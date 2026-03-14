import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from database import player_repo
from events.lfg_handler import LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL
from utils.cooldown import cooldown

log = logging.getLogger(__name__)


class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="queue", description="Show LFG queue status")
    @cooldown(10)
    async def queue_status(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        user_id = interaction.user.id
        now = datetime.now(timezone.utc)
        lines = []

        for channel_name in (LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL):
            vc = discord.utils.get(guild.voice_channels, name=channel_name)
            if not vc:
                continue

            pool = self.bot.lfg_pools.get(vc.id, {})
            count = len(pool)
            label = "Squad" if "Squad" in channel_name else "Duo"

            if user_id in pool:
                wait = now - pool[user_id]
                minutes = int(wait.total_seconds()) // 60
                seconds = int(wait.total_seconds()) % 60
                lines.append(f"**LFG {label}** — {count} waiting (you, {minutes}m {seconds}s)")
            else:
                lines.append(f"**LFG {label}** — {count} waiting")

        if lines:
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("No LFG channels found.", ephemeral=True)

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
