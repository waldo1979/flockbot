import discord
from discord import app_commands
from discord.ext import commands

from database import feedback_repo, player_repo
from services import feedback_service
from utils.views import FeedbackView


class Feedback(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.rate_teammate_menu = app_commands.ContextMenu(
            name="Rate Teammate",
            callback=self._rate_teammate_context,
        )
        self.bot.tree.add_command(self.rate_teammate_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.rate_teammate_menu.name, type=self.rate_teammate_menu.type)

    async def _show_feedback_view(
        self, interaction: discord.Interaction, target: discord.Member
    ) -> None:
        from_id = str(interaction.user.id)
        target_id = str(target.id)

        if from_id == target_id:
            await interaction.response.send_message(
                "You cannot rate yourself.", ephemeral=True
            )
            return

        # Verify both are registered
        from_player = await player_repo.get_player(self.bot.db, from_id)
        target_player = await player_repo.get_player(self.bot.db, target_id)

        if not from_player:
            await interaction.response.send_message(
                "You must be registered first. Use `/register <pubg_name>`.",
                ephemeral=True,
            )
            return

        if not target_player:
            await interaction.response.send_message(
                f"{target.display_name} is not registered.", ephemeral=True
            )
            return

        view = FeedbackView(target_id, target_player["pubg_name"])
        await interaction.response.send_message(
            f"Rate **{target_player['pubg_name']}**:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="feedback", description="Rate a teammate")
    @app_commands.describe(player="The player to rate")
    async def feedback(
        self, interaction: discord.Interaction, player: discord.Member
    ) -> None:
        await self._show_feedback_view(interaction, player)

    async def _rate_teammate_context(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        await self._show_feedback_view(interaction, member)

    @app_commands.command(name="unblock", description="Remove a Never Again block")
    @app_commands.describe(player="The player to unblock")
    async def unblock(
        self, interaction: discord.Interaction, player: discord.Member
    ) -> None:
        from_id = str(interaction.user.id)
        target_id = str(player.id)
        removed = await feedback_service.remove_block(self.bot.db, from_id, target_id)
        if removed:
            await interaction.response.send_message(
                f"Block on **{player.display_name}** removed.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"You don't have a block on **{player.display_name}**.", ephemeral=True
            )

    @app_commands.command(name="buddies", description="List your confirmed best buddies")
    async def buddies(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)
        buddy_ids = await feedback_repo.get_confirmed_buddies(self.bot.db, discord_id)

        if not buddy_ids:
            await interaction.response.send_message(
                "You have no confirmed buddies yet.", ephemeral=True
            )
            return

        lines = []
        for bid in buddy_ids:
            p = await player_repo.get_player(self.bot.db, bid)
            name = p["pubg_name"] if p else f"<{bid}>"
            lines.append(f"- **{name}**")

        await interaction.response.send_message(
            "Your best buddies:\n" + "\n".join(lines), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Feedback(bot))
