import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from database import feedback_repo, player_repo
from services.matchmaker import QueuedPlayer, form_squads, form_duos, NEW_PLAYER_DEFAULT_ADR
from utils.embeds import squad_embed

log = logging.getLogger(__name__)

LFG_SQUAD_CHANNEL = "LFG Squad"
LFG_DUO_CHANNEL = "LFG Duo"
SQUADS_CATEGORY = "SQUADS"
BUDDY_WAIT_MINUTES = 5

# In-memory pool: channel_id -> set of discord_ids
_pools: dict[int, set[int]] = {}
# Counter for temp channel naming
_group_counter = 0
# Track buddy notifications to avoid spam: (buddy_id, channel_id) -> timestamp
_buddy_notified: dict[tuple[int, int], datetime] = {}


class LFGHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _find_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        for cat in guild.categories:
            if cat.name.upper() == SQUADS_CATEGORY:
                return cat
        return None

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild

        # --- Player joined an LFG channel ---
        if after.channel and after.channel.name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            channel = after.channel
            pool = _pools.setdefault(channel.id, set())

            # Must be registered
            player = await player_repo.get_player(self.bot.db, str(member.id))
            if not player:
                try:
                    await member.move_to(None)
                except discord.Forbidden:
                    pass
                try:
                    await member.send(
                        "You must register before using LFG. Use `/register <pubg_name>` in the server."
                    )
                except discord.Forbidden:
                    pass
                return

            pool.add(member.id)
            log.info("%s joined %s pool (%d waiting)", player["pubg_name"], channel.name, len(pool))

            # Notify buddies
            await self._notify_buddies(member, channel)

            # Try to form groups
            await self._try_form(channel)

        # --- Player left an LFG channel ---
        if before.channel and before.channel.name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            pool = _pools.get(before.channel.id)
            if pool:
                pool.discard(member.id)

        # --- Temp channel became empty → delete it ---
        if before.channel and before.channel != after.channel:
            if before.channel.name.startswith(("Squad #", "Duo #")):
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Empty temp LFG channel")
                        log.info("Deleted empty temp channel: %s", before.channel.name)
                    except discord.Forbidden:
                        log.warning("Cannot delete temp channel %s", before.channel.name)

    async def _notify_buddies(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        discord_id = str(member.id)
        buddy_ids = await feedback_repo.get_confirmed_buddies(self.bot.db, discord_id)

        for bid in buddy_ids:
            bid_int = int(bid)

            # Already in the pool?
            pool = _pools.get(channel.id, set())
            if bid_int in pool:
                continue

            # Already notified recently?
            key = (bid_int, channel.id)
            last = _buddy_notified.get(key)
            if last and (datetime.now(timezone.utc) - last).total_seconds() < BUDDY_WAIT_MINUTES * 60:
                continue

            # Is the buddy online in this guild?
            buddy_member = member.guild.get_member(bid_int)
            if not buddy_member or buddy_member.status == discord.Status.offline:
                continue

            buddy_player = await player_repo.get_player(self.bot.db, bid)
            if not buddy_player:
                continue

            _buddy_notified[key] = datetime.now(timezone.utc)

            # Find a text channel to send the notification
            text_channel = self._find_text_channel(member.guild)
            if text_channel:
                await text_channel.send(
                    f"{buddy_member.mention}, your buddy **{member.display_name}** is looking for a "
                    f"{'squad' if 'Squad' in channel.name else 'duo'}! "
                    f"Join **{channel.name}** to play together."
                )

    def _find_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        for ch in guild.text_channels:
            if ch.name in ("bot-commands", "general", "lfg"):
                if ch.permissions_for(guild.me).send_messages:
                    return ch
        return None

    async def _try_form(self, channel: discord.VoiceChannel) -> None:
        is_squad = channel.name == LFG_SQUAD_CHANNEL
        group_size = 4 if is_squad else 2
        pool = _pools.get(channel.id, set())

        if len(pool) < group_size:
            return

        # Build QueuedPlayer list
        queued = []
        for uid in list(pool):
            player = await player_repo.get_player(self.bot.db, str(uid))
            if not player:
                continue

            if is_squad:
                adr = player["squad_fpp_adr"] or NEW_PLAYER_DEFAULT_ADR
            else:
                adr = player["duo_fpp_adr"] or NEW_PLAYER_DEFAULT_ADR

            queued.append(QueuedPlayer(
                discord_id=str(uid),
                pubg_name=player["pubg_name"],
                adr=adr,
            ))

        if len(queued) < group_size:
            return

        # Run matchmaker
        if is_squad:
            groups = await form_squads(self.bot.db, queued)
        else:
            groups = await form_duos(self.bot.db, queued)

        if not groups:
            return

        category = self._find_category(channel.guild)
        text_channel = self._find_text_channel(channel.guild)

        for group in groups:
            await self._create_group(channel, group, is_squad, category, text_channel)

    async def _create_group(
        self,
        lfg_channel: discord.VoiceChannel,
        group: list[QueuedPlayer],
        is_squad: bool,
        category: discord.CategoryChannel | None,
        text_channel: discord.TextChannel | None,
    ) -> None:
        global _group_counter
        _group_counter += 1

        prefix = "Squad" if is_squad else "Duo"
        name = f"{prefix} #{_group_counter}"

        # Create temp voice channel
        try:
            temp_channel = await lfg_channel.guild.create_voice_channel(
                name=name,
                category=category,
                reason="LFG group formed",
            )
        except discord.Forbidden:
            log.error("Cannot create voice channel %s", name)
            return

        # Move players and remove from pool
        pool = _pools.get(lfg_channel.id, set())
        group_dicts = []
        for p in group:
            uid = int(p.discord_id)
            pool.discard(uid)
            member = lfg_channel.guild.get_member(uid)
            if member:
                try:
                    await member.move_to(temp_channel)
                except discord.Forbidden:
                    log.warning("Cannot move %s", p.pubg_name)

            player = await player_repo.get_player(self.bot.db, p.discord_id)
            tier = None
            if player:
                tier = player["squad_fpp_tier"] if is_squad else player["duo_fpp_tier"]
            group_dicts.append({"pubg_name": p.pubg_name, "tier": tier})

        # Announce in text channel
        if text_channel:
            embed = squad_embed(group_dicts, _group_counter, prefix)
            await text_channel.send(embed=embed)

        log.info("Formed %s with %s", name, [p.pubg_name for p in group])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LFGHandler(bot))
