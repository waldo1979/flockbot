import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from database.connection import init_db, close_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("flockbot")


class FlockBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.db: None = None
        self._synced = False
        # Shared LFG pool state: channel_id -> set of discord user ids
        self.lfg_pools: dict[int, set[int]] = {}

    async def setup_hook(self) -> None:
        self.db = await init_db(config.DATABASE_PATH)

        extensions = [
            "commands.admin",
            "commands.stats",
            "commands.feedback",
            "commands.queue",
            "events.on_ready",
            "events.lfg_handler",
            "events.voice_tracker",
        ]
        for ext in extensions:
            await self.load_extension(ext)
            log.info("Loaded extension %s", ext)

        self.tree.on_error = self._on_app_command_error

    async def on_ready(self) -> None:
        if not self._synced:
            if config.GUILD_ID:
                guild = discord.Object(id=config.GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Synced commands to guild %s", config.GUILD_ID)
            else:
                await self.tree.sync()
                log.info("Synced commands globally")
            self._synced = True
        log.info("Flockbot ready as %s", self.user)

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You don't have permission to use this command."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"Command on cooldown. Try again in {error.retry_after:.0f}s."
        else:
            log.exception("Unhandled app command error", exc_info=error)
            msg = "Something went wrong. Please try again later."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def close(self) -> None:
        if self.db:
            await close_db(self.db)
        await super().close()


def main() -> None:
    bot = FlockBot()
    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
