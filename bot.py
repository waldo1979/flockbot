import logging

import discord
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

    async def setup_hook(self) -> None:
        self.db = await init_db(config.DATABASE_PATH)

        extensions = [
            "commands.admin",
        ]
        for ext in extensions:
            await self.load_extension(ext)
            log.info("Loaded extension %s", ext)

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

    async def close(self) -> None:
        if self.db:
            await close_db(self.db)
        await super().close()


def main() -> None:
    bot = FlockBot()
    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
