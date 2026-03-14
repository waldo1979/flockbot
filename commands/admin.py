import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import player_repo

log = logging.getLogger(__name__)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    admin_group = app_commands.Group(
        name="admin", description="Bot administration commands"
    )

    @admin_group.command(name="sync", description="Sync slash commands to Discord")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction) -> None:
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
        else:
            synced = await self.bot.tree.sync()
        await interaction.response.send_message(
            f"Synced {len(synced)} commands.", ephemeral=True
        )

    @admin_group.command(
        name="cleanup", description="Run stale data cleanup manually"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def cleanup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        cursor = await db.execute(
            "DELETE FROM feedback WHERE created_at < datetime('now', '-84 days')"
        )
        deleted = cursor.rowcount
        await db.commit()
        await interaction.followup.send(
            f"Cleanup complete. Deleted {deleted} stale feedback rows.",
            ephemeral=True,
        )


    @admin_group.command(
        name="transfer",
        description="Transfer a PUBG account to a different Discord user",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        pubg_name="The PUBG in-game name to transfer",
        to_player="Discord user to transfer the PUBG account to",
    )
    async def transfer(
        self,
        interaction: discord.Interaction,
        pubg_name: str,
        to_player: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db

        # Look up the PUBG name in the database
        source = await player_repo.get_player_by_pubg_name(db, pubg_name)
        if not source:
            await interaction.followup.send(
                f"No registered player with PUBG name **{pubg_name}**.",
                ephemeral=True,
            )
            return

        # Check the target isn't already registered to a different PUBG account
        target = await player_repo.get_player(db, str(to_player.id))
        if target:
            await interaction.followup.send(
                f"{to_player.mention} is already registered as "
                f"**{target['pubg_name']}**. They must `/register` the "
                "new name themselves after the old link is removed.",
                ephemeral=True,
            )
            return

        old_discord_id = source["discord_id"]
        pubg_id = source["pubg_id"]

        # Delete the old row, then upsert for the new owner
        await db.execute(
            "DELETE FROM players WHERE discord_id = ?", (old_discord_id,)
        )
        await player_repo.upsert_player(
            db, str(to_player.id), pubg_id, pubg_name
        )

        # Set the new owner's nickname
        try:
            await to_player.edit(nick=pubg_name)
        except discord.Forbidden:
            log.warning(
                "Cannot set nickname for %s (likely server owner)", to_player
            )

        await interaction.followup.send(
            f"Transferred **{pubg_name}** (was <@{old_discord_id}>) to "
            f"{to_player.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
