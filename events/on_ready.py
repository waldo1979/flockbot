import logging

from discord.ext import commands

log = logging.getLogger(__name__)


class OnReady(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("OnReady cog active — background tasks will be added in later phases")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OnReady(bot))
