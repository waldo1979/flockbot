import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import player_repo
from events.lfg_handler import LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL
from services.matchmaker import QueuePreference, RELAXATION_START_SECS, RELAXATION_FULL_SECS
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
