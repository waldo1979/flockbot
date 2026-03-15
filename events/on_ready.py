import logging

from discord.ext import commands, tasks

from database import cache_repo, player_repo
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

        # Refresh registered players
        players = await player_repo.get_all_players(self.bot.db)
        log.info("Refreshing stats for %d registered players", len(players))

        for player in players:
            try:
                pubg_id = player.get("pubg_id")
                if not pubg_id:
                    continue
                computed = await refresh_player_stats(
                    self.bot.db,
                    self.api,
                    pubg_id,
                    self.current_season,
                    self.previous_season,
                )
                if computed:
                    await player_repo.update_cached_stats(
                        self.bot.db,
                        discord_id=player["discord_id"],
                        squad_fpp_adr=computed.squad_fpp_adr,
                        squad_fpp_tier=computed.squad_fpp_tier,
                        squad_fpp_matches=computed.squad_fpp_matches,
                        duo_fpp_adr=computed.duo_fpp_adr,
                        duo_fpp_tier=computed.duo_fpp_tier,
                        duo_fpp_matches=computed.duo_fpp_matches,
                        adr_season=computed.adr_season,
                    )
            except Exception:
                log.exception("Failed to refresh stats for %s", player["pubg_name"])

        # Refresh recently looked-up cached players
        cached_players = await cache_repo.get_active_cached_players(
            self.bot.db, days=14
        )
        if cached_players:
            log.info(
                "Refreshing stats for %d cached players", len(cached_players)
            )
            for cached in cached_players:
                try:
                    computed = await refresh_player_stats(
                        self.bot.db,
                        self.api,
                        cached["pubg_id"],
                        self.current_season,
                        self.previous_season,
                    )
                    if computed:
                        await cache_repo.update_cached_stats(
                            self.bot.db,
                            pubg_id=cached["pubg_id"],
                            squad_fpp_adr=computed.squad_fpp_adr,
                            squad_fpp_tier=computed.squad_fpp_tier,
                            squad_fpp_matches=computed.squad_fpp_matches,
                            duo_fpp_adr=computed.duo_fpp_adr,
                            duo_fpp_tier=computed.duo_fpp_tier,
                            duo_fpp_matches=computed.duo_fpp_matches,
                            adr_season=computed.adr_season,
                        )
                except Exception:
                    log.exception(
                        "Failed to refresh cached stats for %s",
                        cached["pubg_name"],
                    )

        # Clean up stale cache entries
        deleted = await cache_repo.delete_stale_cached_players(
            self.bot.db, days=30
        )
        if deleted:
            log.info("Deleted %d stale cached player entries", deleted)

    @refresh_all_stats.before_loop
    async def before_refresh_stats(self) -> None:
        await self.bot.wait_until_ready()

    @refresh_season.before_loop
    async def before_refresh_season(self) -> None:
        await self.bot.wait_until_ready()



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackgroundTasks(bot))
