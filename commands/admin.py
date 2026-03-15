import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import player_repo
from utils.channel_names import generate_channel_name

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
            "DELETE FROM player_cache WHERE last_lookup < datetime('now', '-30 days')"
        )
        deleted = cursor.rowcount
        await db.commit()
        await interaction.followup.send(
            f"Cleanup complete. Deleted {deleted} stale cached player entries.",
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


    @admin_group.command(
        name="testmatch",
        description="Create a temp voice channel and move a player into it (for testing)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(player="The player to move into the test channel")
    async def testmatch(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Find the PUBG VOICE category
        category = None
        for cat in guild.categories:
            if cat.name.upper() == "PUBG VOICE":
                category = cat
                break
        if not category:
            await interaction.followup.send(
                "PUBG VOICE category not found.", ephemeral=True
            )
            return

        # Player must be in a voice channel
        if not player.voice or not player.voice.channel:
            await interaction.followup.send(
                f"{player.mention} is not in a voice channel.", ephemeral=True
            )
            return

        name = generate_channel_name()

        try:
            temp_channel = await guild.create_voice_channel(
                name=name,
                category=category,
                reason="Admin test match",
            )
        except discord.Forbidden as e:
            await interaction.followup.send(
                f"Cannot create voice channel: {e}", ephemeral=True
            )
            return

        # Set permissions
        try:
            await temp_channel.set_permissions(
                guild.default_role, connect=False,
            )
            await temp_channel.set_permissions(
                guild.me,
                connect=True, move_members=True, manage_channels=True,
            )
            await temp_channel.set_permissions(player, connect=True)
        except discord.Forbidden:
            log.warning("Could not set permissions on %s", name)

        # Move player
        try:
            await player.move_to(temp_channel)
        except discord.Forbidden:
            await interaction.followup.send(
                f"Cannot move {player.mention} — missing Move Members permission.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Created **{name}** and moved {player.mention} into it.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
