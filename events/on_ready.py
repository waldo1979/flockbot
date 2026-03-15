import logging

from discord.ext import commands, tasks

from database import player_repo
from services.pubg_api import PUBGApiClient
from services.stats_service import refresh_player_stats

log = logging.getLogger(__name__)


class BackgroundTasks(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.api = PUBGApiClient()
        self.current_season: str | None = None
        self.previous_season: str | None = None

    async def cog_unload(self) -> None:
        self.refresh_all_stats.cancel()
        self.refresh_season.cancel()
        await self.api.close()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.refresh_season.is_running():
            self.refresh_season.start()
        if not self.refresh_all_stats.is_running():
            self.refresh_all_stats.start()
        log.info("Background tasks started")

    @tasks.loop(hours=24)
    async def refresh_season(self) -> None:
        season_id = await self.api.get_current_season_id()
        if season_id and season_id != self.current_season:
            self.previous_season = self.current_season
            self.current_season = season_id
            log.info("Season updated: %s", season_id)

            # Propagate to Stats cog
            stats_cog = self.bot.get_cog("Stats")
            if stats_cog:
                stats_cog.previous_season = self.previous_season
                stats_cog.current_season = self.current_season

    @tasks.loop(hours=2)
    async def refresh_all_stats(self) -> None:
        if not self.current_season:
            return

        players = await player_repo.get_all_players(self.bot.db)
        log.info("Refreshing stats for %d players", len(players))

        for player in players:
            try:
                await refresh_player_stats(
                    self.bot.db,
                    self.api,
                    player["discord_id"],
                    self.current_season,
                    self.previous_season,
                )
            except Exception:
                log.exception("Failed to refresh stats for %s", player["pubg_name"])

    @refresh_all_stats.before_loop
    async def before_refresh_stats(self) -> None:
        await self.bot.wait_until_ready()

    @refresh_season.before_loop
    async def before_refresh_season(self) -> None:
        await self.bot.wait_until_ready()



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackgroundTasks(bot))
