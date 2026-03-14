import logging

import discord
from discord import app_commands
from discord.ext import commands

from database import player_repo
from events.lfg_handler import LFG_SQUAD_CHANNEL, LFG_DUO_CHANNEL, _pools
from utils.cooldown import cooldown
from utils.embeds import queue_embed

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

        embeds = []
        for channel_name, mode in [(LFG_SQUAD_CHANNEL, "squad"), (LFG_DUO_CHANNEL, "duo")]:
            # Find the voice channel
            vc = discord.utils.get(guild.voice_channels, name=channel_name)
            if not vc:
                continue

            pool = _pools.get(vc.id, set())
            log.info("Queue check: %s (vc.id=%d) pool=%s, all_pools=%s (pools id=%d)", channel_name, vc.id, pool, dict(_pools), id(_pools))
            players = []
            for uid in pool:
                player = await player_repo.get_player(self.bot.db, str(uid))
                if player:
                    tier = player["squad_fpp_tier"] if mode == "squad" else player["duo_fpp_tier"]
                    players.append({"pubg_name": player["pubg_name"], "tier": tier})

            embeds.append(queue_embed(mode, players))

        if embeds:
            await interaction.response.send_message(embeds=embeds)
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
            pool = _pools.get(vc.id, set())
            if player.id in pool:
                pool.discard(player.id)
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
