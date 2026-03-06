import discord
from discord import app_commands
from discord.ext import commands

import config


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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
