import asyncio
import logging
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import feedback_repo, player_repo
from services.matchmaker import (
    QueuedPlayer, QueuePreference, form_squads, form_duos, NEW_PLAYER_DEFAULT_ADR,
)
from utils.embeds import squad_embed
from utils.channel_names import generate_channel_name

log = logging.getLogger(__name__)

LFG_SQUAD_CHANNEL = "LFG Squad"
LFG_DUO_CHANNEL = "LFG Duo"
SQUADS_CATEGORY = "PUBG VOICE"
BUDDY_WAIT_MINUTES = 5
TEMP_CHANNEL_GRACE_MINUTES = 10

# Track buddy notifications to avoid spam: (buddy_id, channel_id) -> timestamp
_buddy_notified: dict[tuple[int, int], datetime] = {}
# Track pending deletions so we can cancel if someone rejoins: channel_id -> asyncio.Task
_pending_deletions: dict[int, asyncio.Task] = {}


class LFGHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Rebuild LFG pools from current voice channel members on startup."""
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            for channel_name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
                vc = discord.utils.get(guild.voice_channels, name=channel_name)
                if not vc:
                    log.debug("Channel %s not found in %s", channel_name, guild.name)
                    continue
                pool = self.bot.lfg_pools.setdefault(vc.id, {})
                # vc.voice_states is a dict of {user_id: VoiceState} available
                # even without the members privileged intent.
                for member_id in vc.voice_states:
                    player = await player_repo.get_player(self.bot.db, str(member_id))
                    if player:
                        pool[member_id] = now
                        log.info("Restored %s to %s pool", player["pubg_name"], channel_name)
                if pool:
                    log.info("Restored %d total players to %s pool", len(pool), channel_name)

        if not self.periodic_match.is_running():
            self.periodic_match.start()

    async def cog_unload(self) -> None:
        self.periodic_match.cancel()

    @tasks.loop(seconds=30)
    async def periodic_match(self) -> None:
        """Re-evaluate LFG pools periodically so long-waiters benefit from relaxation."""
        for guild in self.bot.guilds:
            for channel_name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
                vc = discord.utils.get(guild.voice_channels, name=channel_name)
                if not vc:
                    continue
                pool = self.bot.lfg_pools.get(vc.id, {})
                group_size = 4 if channel_name == LFG_SQUAD_CHANNEL else 2
                if len(pool) >= group_size:
                    await self._try_form(vc)

    @periodic_match.before_loop
    async def before_periodic_match(self) -> None:
        await self.bot.wait_until_ready()

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

        # Ignore voice state changes that don't involve a channel switch
        # (e.g., mute, deafen, stream start) — these fire the event but
        # before.channel == after.channel.
        if before.channel == after.channel:
            return

        # --- Player joined an LFG channel ---
        if after.channel and after.channel.name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            channel = after.channel
            pool = self.bot.lfg_pools.setdefault(channel.id, {})

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

            pool[member.id] = datetime.now(timezone.utc)
            log.info("%s joined %s pool (%d waiting)", player["pubg_name"], channel.name, len(pool))

            # Notify buddies
            await self._notify_buddies(member, channel)

            # Try to form groups
            await self._try_form(channel)

        # --- Player left an LFG channel ---
        if before.channel and before.channel.name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            pool = self.bot.lfg_pools.get(before.channel.id)
            if pool:
                pool.pop(member.id, None)

        # --- Someone joined a temp channel → cancel pending deletion ---
        if after.channel and after.channel.category:
            if after.channel.category.name.upper() == SQUADS_CATEGORY:
                task = _pending_deletions.pop(after.channel.id, None)
                if task and not task.done():
                    task.cancel()
                    log.info("Cancelled deletion of %s (player rejoined)", after.channel.name)

        # --- Temp channel became empty → schedule deletion after grace period ---
        if before.channel and before.channel != after.channel:
            if before.channel.category and before.channel.category.name.upper() == SQUADS_CATEGORY:
                if len(before.channel.members) == 0:
                    task = asyncio.create_task(
                        self._delayed_delete(before.channel)
                    )
                    _pending_deletions[before.channel.id] = task

    async def _notify_buddies(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        discord_id = str(member.id)
        buddy_ids = await feedback_repo.get_confirmed_buddies(self.bot.db, discord_id)

        for bid in buddy_ids:
            bid_int = int(bid)

            # Already in the pool?
            pool = self.bot.lfg_pools.get(channel.id, {})
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

    async def _delayed_delete(self, channel: discord.VoiceChannel) -> None:
        """Wait for the grace period, then delete the channel if still empty."""
        try:
            await asyncio.sleep(TEMP_CHANNEL_GRACE_MINUTES * 60)
        except asyncio.CancelledError:
            return
        # Re-check: channel may have been deleted or someone rejoined
        try:
            if len(channel.members) == 0:
                await channel.delete(reason="Empty temp LFG channel (grace period expired)")
                log.info("Deleted empty temp channel: %s", channel.name)
        except discord.NotFound:
            pass  # Already deleted
        except discord.Forbidden:
            log.warning("Cannot delete temp channel %s", channel.name)
        finally:
            _pending_deletions.pop(channel.id, None)

    def _find_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        for ch in guild.text_channels:
            if ch.name in ("bot-commands", "general", "lfg"):
                if ch.permissions_for(guild.me).send_messages:
                    return ch
        return None

    async def _try_form(self, channel: discord.VoiceChannel) -> None:
        is_squad = channel.name == LFG_SQUAD_CHANNEL
        group_size = 4 if is_squad else 2
        pool = self.bot.lfg_pools.get(channel.id, {})

        if len(pool) < group_size:
            return

        # Build QueuedPlayer list
        queued = []
        for uid, join_time in list(pool.items()):
            player = await player_repo.get_player(self.bot.db, str(uid))
            if not player:
                continue

            if is_squad:
                adr = player["squad_fpp_adr"] or NEW_PLAYER_DEFAULT_ADR
            else:
                adr = player["duo_fpp_adr"] or NEW_PLAYER_DEFAULT_ADR

            pref_str = player.get("queue_preference", "skill") or "skill"
            try:
                preference = QueuePreference(pref_str)
            except ValueError:
                preference = QueuePreference.SKILL

            queued.append(QueuedPlayer(
                discord_id=str(uid),
                pubg_name=player["pubg_name"],
                adr=adr,
                join_time=join_time,
                preference=preference,
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
        name = generate_channel_name()

        # Build permission overrides: deny @everyone, allow matched players
        overwrites = {
            lfg_channel.guild.default_role: discord.PermissionOverwrite(connect=False),
            lfg_channel.guild.me: discord.PermissionOverwrite(
                connect=True, move_members=True, manage_channels=True,
            ),
        }
        for p in group:
            member = lfg_channel.guild.get_member(int(p.discord_id))
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=True)

        # Create temp voice channel
        try:
            temp_channel = await lfg_channel.guild.create_voice_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason="LFG group formed",
            )
        except discord.Forbidden:
            log.error("Cannot create voice channel %s", name)
            return

        # Move players and remove from pool
        pool = self.bot.lfg_pools.get(lfg_channel.id, {})
        group_dicts = []
        for p in group:
            uid = int(p.discord_id)
            pool.pop(uid, None)
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
        mode = "Squad" if is_squad else "Duo"
        if text_channel:
            embed = squad_embed(group_dicts, name, mode)
            await text_channel.send(embed=embed)

        log.info("Formed %s with %s", name, [p.pubg_name for p in group])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LFGHandler(bot))
