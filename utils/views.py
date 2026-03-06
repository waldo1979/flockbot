import discord

from services import feedback_service


class ConfirmBlockView(discord.ui.View):
    def __init__(self, from_id: str, target_id: str, target_name: str) -> None:
        super().__init__(timeout=60)
        self.from_id = from_id
        self.target_id = target_id
        self.target_name = target_name

    @discord.ui.button(label="Yes, block permanently", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await feedback_service.record_block(interaction.client.db, self.from_id, self.target_id)
        await interaction.response.edit_message(
            content=f"**{self.target_name}** has been blocked. You will never be grouped together. Use `/unblock` to undo.",
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class FeedbackView(discord.ui.View):
    def __init__(self, target_id: str, target_name: str) -> None:
        super().__init__(timeout=3600)
        self.target_id = target_id
        self.target_name = target_name

    @discord.ui.button(label="Thumbs Up", style=discord.ButtonStyle.green, emoji="\U0001f44d")
    async def thumbs_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from_id = str(interaction.user.id)
        err = await feedback_service.record_feedback(interaction.client.db, from_id, self.target_id, 1)
        if err:
            await interaction.response.edit_message(content=err, view=None)
        else:
            await interaction.response.edit_message(
                content=f"Positive feedback recorded for **{self.target_name}**.",
                view=None,
            )
        self.stop()

    @discord.ui.button(label="Thumbs Down", style=discord.ButtonStyle.red, emoji="\U0001f44e")
    async def thumbs_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from_id = str(interaction.user.id)
        err = await feedback_service.record_feedback(interaction.client.db, from_id, self.target_id, -1)
        if err:
            await interaction.response.edit_message(content=err, view=None)
        else:
            await interaction.response.edit_message(
                content=f"Feedback recorded for **{self.target_name}**.",
                view=None,
            )
        self.stop()

    @discord.ui.button(label="Never Again", style=discord.ButtonStyle.danger, emoji="\U0001f6ab")
    async def never_again(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from_id = str(interaction.user.id)
        confirm_view = ConfirmBlockView(from_id, self.target_id, self.target_name)
        await interaction.response.edit_message(
            content=f"Are you sure you want to block **{self.target_name}** permanently? They will never be in your group.",
            view=confirm_view,
        )
        self.stop()

    @discord.ui.button(label="Best Buddy", style=discord.ButtonStyle.blurple, emoji="\u2b50")
    async def best_buddy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from_id = str(interaction.user.id)
        mutual = await feedback_service.record_buddy_request(interaction.client.db, from_id, self.target_id)
        if mutual:
            msg = f"You and **{self.target_name}** are now best buddies! The matchmaker will always group you together."
        else:
            msg = f"Buddy request sent to **{self.target_name}**. If they also mark you, you'll become best buddies."
        # Also record as positive feedback
        await feedback_service.record_feedback(interaction.client.db, from_id, self.target_id, 1)
        await interaction.response.edit_message(content=msg, view=None)
        self.stop()
