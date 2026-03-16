import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import player_repo, feedback_repo
from events.lfg_handler import LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL, CREATE_LOBBY_CHANNEL, SQUADS_CATEGORY
from services.matchmaker import (
    QueuedPlayer, QueuePreference, NEW_PLAYER_DEFAULT_ADR,
    RELAXATION_START_SECS, RELAXATION_FULL_SECS,
    _skill_score, _social_score, _has_block, _total_score,
)
from utils.cooldown import cooldown

log = logging.getLogger(__name__)


def _format_countdown(secs: int) -> str:
    """Format seconds as Xm Ys."""
    m, s = divmod(secs, 60)
    return f"{m}m {s}s"


def _queue_status_line(wait_secs: float, preference: str, group_size: int, pool_size: int) -> str:
    """Build a concise status line for a queued player."""
    effective = wait_secs * 2.0 if preference == "fast" else wait_secs
    parts = [f"Waiting {_format_countdown(int(wait_secs))}"]

    # Need count — how many more players needed
    need = group_size - pool_size
    if need > 0:
        parts.append(f"need {need} more")

    # Laxative status
    if effective < RELAXATION_START_SECS:
        secs_until = int((RELAXATION_START_SECS - effective) / (2.0 if preference == "fast" else 1.0))
        parts.append(f"laxative in {_format_countdown(secs_until)}")
    elif effective < RELAXATION_FULL_SECS:
        secs_until = int((RELAXATION_FULL_SECS - effective) / (2.0 if preference == "fast" else 1.0))
        parts.append(f"fully open in {_format_countdown(secs_until)}")
    else:
        parts.append("wide open")

    return " · ".join(parts)


class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="queue", description="Show your LFG queue status")
    @cooldown(10)
    async def queue_status(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        user_id = interaction.user.id
        now = datetime.now(timezone.utc)

        # Find which queue the player is in
        for channel_name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            vc = discord.utils.get(guild.voice_channels, name=channel_name)
            if not vc:
                continue
            pool = self.bot.lfg_pools.get(vc.id, {})
            if user_id in pool:
                player = await player_repo.get_player(self.bot.db, str(user_id))
                pref = (player.get("queue_preference") or "skill") if player else "skill"
                label = "Squad" if "Squad" in channel_name else "Duo"
                group_size = 4 if "Squad" in channel_name else 2
                wait_secs = (now - pool[user_id]).total_seconds()

                status = _queue_status_line(wait_secs, pref, group_size, len(pool))
                await interaction.response.send_message(
                    f"**LFG {label}** — {status}", ephemeral=True
                )
                return

        await interaction.response.send_message("You're not in a queue.", ephemeral=True)

    @app_commands.command(name="queuepref", description="Set your matching preference: skill (strict) or fast (relaxes quicker)")
    @app_commands.describe(preference="Matching mode: 'skill' for tight matches, 'fast' for quicker groups")
    @app_commands.choices(preference=[
        app_commands.Choice(name="Skill (tighter matches)", value="skill"),
        app_commands.Choice(name="Fast (quicker groups)", value="fast"),
    ])
    @cooldown(10)
    async def queue_pref(
        self, interaction: discord.Interaction, preference: app_commands.Choice[str]
    ) -> None:
        player = await player_repo.get_player(self.bot.db, str(interaction.user.id))
        if not player:
            await interaction.response.send_message(
                "You must register first. Use `/register <pubg_name>`.", ephemeral=True
            )
            return

        await player_repo.set_queue_preference(self.bot.db, str(interaction.user.id), preference.value)
        label = "Skill (tighter matches)" if preference.value == "skill" else "Fast (quicker groups)"
        await interaction.response.send_message(
            f"Queue preference set to **{label}**.", ephemeral=True
        )

    @app_commands.command(name="open", description="Toggle channel lock — unlock or re-lock your matched channel")
    @cooldown(10)
    async def open_channel(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return

        vc = member.voice.channel
        # Must be under PUBG VOICE category, not a lobby channel
        lobby_names = {LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL, CREATE_LOBBY_CHANNEL}
        if (
            not vc.category
            or vc.category.name.upper() != SQUADS_CATEGORY
            or vc.name in lobby_names
        ):
            await interaction.response.send_message(
                "This command only works in a matched squad/duo channel.", ephemeral=True
            )
            return

        everyone_role = interaction.guild.default_role
        overwrites = vc.overwrites_for(everyone_role)

        try:
            if overwrites.connect is False:
                # Currently locked → unlock
                await vc.set_permissions(everyone_role, overwrite=None)
                await interaction.response.send_message("Channel unlocked — anyone can join.", ephemeral=True)
            else:
                # Currently open → lock
                await vc.set_permissions(everyone_role, connect=False)
                await interaction.response.send_message("Channel locked — only permitted players can join.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to modify this channel.", ephemeral=True
            )

    @app_commands.command(name="fill", description="Pull the best matching player from LFG into your channel")
    @cooldown(30)
    async def fill(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return

        vc = member.voice.channel
        lobby_names = {LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL, CREATE_LOBBY_CHANNEL}
        if (
            not vc.category
            or vc.category.name.upper() != SQUADS_CATEGORY
            or vc.name in lobby_names
        ):
            await interaction.response.send_message(
                "This command only works in a matched squad/duo channel.", ephemeral=True
            )
            return

        # Determine which LFG queue to pull from based on channel size
        # Channels with user_limit <= 2 or only 1 member are duo; otherwise squad
        is_squad = vc.user_limit != 2
        lfg_name = LFG_SQUAD_CHANNEL if is_squad else LFG_DUO_CHANNEL
        lfg_vc = discord.utils.get(interaction.guild.voice_channels, name=lfg_name)
        if not lfg_vc:
            await interaction.response.send_message("LFG channel not found.", ephemeral=True)
            return

        pool = self.bot.lfg_pools.get(lfg_vc.id, {})
        if not pool:
            await interaction.response.send_message(
                f"No players in {lfg_name} queue.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Build QueuedPlayer list for current channel members
        channel_players = []
        for m in vc.members:
            player = await player_repo.get_player(self.bot.db, str(m.id))
            if not player:
                continue
            adr = (player["squad_fpp_adr"] if is_squad else player["duo_fpp_adr"]) or NEW_PLAYER_DEFAULT_ADR
            channel_players.append(QueuedPlayer(
                discord_id=str(m.id), pubg_name=player["pubg_name"], adr=adr,
            ))

        # Score each candidate in the queue
        best_candidate = None
        best_score = float("-inf")
        best_uid = None

        for uid, join_time in list(pool.items()):
            player = await player_repo.get_player(self.bot.db, str(uid))
            if not player:
                continue

            adr = (player["squad_fpp_adr"] if is_squad else player["duo_fpp_adr"]) or NEW_PLAYER_DEFAULT_ADR
            pref_str = player.get("queue_preference", "skill") or "skill"
            try:
                preference = QueuePreference(pref_str)
            except ValueError:
                preference = QueuePreference.SKILL
            candidate = QueuedPlayer(
                discord_id=str(uid), pubg_name=player["pubg_name"], adr=adr,
                join_time=join_time, preference=preference,
            )

            # Check for blocks against any channel member
            test_group = channel_players + [candidate]
            if await _has_block(self.bot.db, test_group):
                continue

            # Score using full matchmaker logic (includes relaxation from wait time)
            score = await _total_score(self.bot.db, test_group)

            if score > best_score:
                best_score = score
                best_candidate = candidate
                best_uid = uid

        if not best_candidate:
            await interaction.followup.send(
                "No compatible players in the queue.", ephemeral=True
            )
            return

        # Move the player into the channel
        target = interaction.guild.get_member(best_uid)
        if not target:
            await interaction.followup.send("Could not find the matched player.", ephemeral=True)
            return

        # Grant connect permission and move
        try:
            await vc.set_permissions(target, connect=True)
            await target.move_to(vc)
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to move players.", ephemeral=True
            )
            return

        # Remove from LFG pool
        pool.pop(best_uid, None)

        await interaction.followup.send(
            f"**{best_candidate.pubg_name}** pulled from queue into your channel.",
            ephemeral=True,
        )

    @app_commands.command(name="kick", description="(Admin) Remove a player from LFG")
    @app_commands.describe(player="The player to kick from the LFG queue")
    @app_commands.checks.has_permissions(administrator=True)
    async def kick(
        self, interaction: discord.Interaction, player: discord.Member
    ) -> None:
        guild = interaction.guild
        if not guild:
            return

        removed = False
        for channel_name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            vc = discord.utils.get(guild.voice_channels, name=channel_name)
            if not vc:
                continue
            pool = self.bot.lfg_pools.get(vc.id, {})
            if player.id in pool:
                pool.pop(player.id, None)
                # Also disconnect from voice
                try:
                    await player.move_to(None)
                except discord.Forbidden:
                    pass
                removed = True

        if removed:
            await interaction.response.send_message(
                f"Removed **{player.display_name}** from LFG.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"**{player.display_name}** is not in any LFG queue.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Queue(bot))
