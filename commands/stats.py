import logging

import discord
from discord import app_commands
from discord.ext import commands

from database import player_repo
from services.pubg_api import PUBGApiClient
from services.stats_service import (
    get_effective_adr,
    refresh_player_stats,
    MIN_MATCHES_FOR_ADR,
)
from events.voice_tracker import refresh_registered_cache
from utils.cooldown import cooldown
from utils.embeds import stats_embed, leaderboard_embed

log = logging.getLogger(__name__)


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.api = PUBGApiClient()
        self.current_season: str | None = None
        self.previous_season: str | None = None

    async def cog_unload(self) -> None:
        await self.api.close()

    async def _ensure_season(self) -> str | None:
        if not self.current_season:
            self.current_season = await self.api.get_current_season_id()
        return self.current_season

    @app_commands.command(
        name="register", description="Link your Discord account to your PUBG name"
    )
    @app_commands.describe(pubg_name="Your PUBG in-game name (PC/Steam)")
    @cooldown(60)
    async def register(
        self, interaction: discord.Interaction, pubg_name: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Look up player on PUBG API
        player_info = await self.api.get_player_by_name(pubg_name)
        if not player_info:
            await interaction.followup.send(
                f"Could not find PUBG player **{pubg_name}** on Steam. "
                "Check the spelling and try again.",
                ephemeral=True,
            )
            return

        discord_id = str(interaction.user.id)

        # Check if this PUBG account is already claimed by another Discord user
        existing = await player_repo.get_player_by_pubg_id(
            self.bot.db, player_info.account_id
        )
        if existing and existing["discord_id"] != discord_id:
            await interaction.followup.send(
                f"**{player_info.name}** is already registered to another player. "
                "Contact an admin if this is your account.",
                ephemeral=True,
            )
            return

        # Save to database
        await player_repo.upsert_player(
            self.bot.db, discord_id, player_info.account_id, player_info.name
        )
        refresh_registered_cache(discord_id)

        # Set server nickname
        try:
            await interaction.user.edit(nick=player_info.name)
        except discord.Forbidden:
            log.warning(
                "Cannot set nickname for %s (likely server owner)", interaction.user
            )

        # Fetch initial stats
        season = await self._ensure_season()
        if season:
            await refresh_player_stats(
                self.bot.db, self.api, discord_id, season, self.previous_season
            )

        player = await player_repo.get_player(self.bot.db, discord_id)
        embed = self._build_stats_embed(player, season)
        await interaction.followup.send(
            f"Registered as **{player_info.name}**!", embed=embed, ephemeral=True
        )

    @app_commands.command(
        name="stats", description="Show your PUBG stats, or look up a registered player"
    )
    @app_commands.describe(pubg_name="Optional: look up a registered player by PUBG name")
    @cooldown(30)
    async def stats(
        self, interaction: discord.Interaction, pubg_name: str | None = None
    ) -> None:
        if pubg_name:
            player = await player_repo.get_player_by_pubg_name(
                self.bot.db, pubg_name
            )
            if not player:
                await interaction.response.send_message(
                    f"No registered player named **{pubg_name}**.",
                    ephemeral=True,
                )
                return

            season = await self._ensure_season()
            embed = self._build_stats_embed(player, season)
            await interaction.response.send_message(embed=embed)
            return

        # No argument — show own stats
        discord_id = str(interaction.user.id)
        player = await player_repo.get_player(self.bot.db, discord_id)
        if not player:
            await interaction.response.send_message(
                "You are not registered. Use `/register <pubg_name>` first.",
                ephemeral=True,
            )
            return

        season = await self._ensure_season()
        embed = self._build_stats_embed(player, season)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="lookup", description="Look up another player's stats"
    )
    @app_commands.describe(player="The player to look up")
    @cooldown(15)
    async def lookup(
        self, interaction: discord.Interaction, player: discord.Member
    ) -> None:
        target = await player_repo.get_player(self.bot.db, str(player.id))
        if not target:
            await interaction.response.send_message(
                f"{player.display_name} is not registered.", ephemeral=True
            )
            return

        season = await self._ensure_season()
        embed = self._build_stats_embed(target, season)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="refresh", description="Force-refresh your stats from the PUBG API"
    )
    @cooldown(300)
    async def refresh(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)
        player = await player_repo.get_player(self.bot.db, discord_id)
        if not player:
            await interaction.response.send_message(
                "You are not registered. Use `/register <pubg_name>` first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        season = await self._ensure_season()
        if season:
            await refresh_player_stats(
                self.bot.db, self.api, discord_id, season, self.previous_season
            )

        player = await player_repo.get_player(self.bot.db, discord_id)
        embed = self._build_stats_embed(player, season)
        await interaction.followup.send("Stats refreshed!", embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Server ADR leaderboard")
    @cooldown(60)
    @app_commands.describe(mode="Game mode")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Squad FPP", value="squad-fpp"),
            app_commands.Choice(name="Duo FPP", value="duo-fpp"),
        ]
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] = None,
    ) -> None:
        selected_mode = mode.value if mode else "squad-fpp"
        season = await self._ensure_season()
        players = await player_repo.get_leaderboard(self.bot.db, selected_mode)
        embed = leaderboard_embed(players, selected_mode, season)
        await interaction.response.send_message(embed=embed)

    def _build_stats_embed(
        self, player: dict, season: str | None
    ) -> discord.Embed:
        squad_fb = player["squad_fpp_matches"] and player["squad_fpp_matches"] < MIN_MATCHES_FOR_ADR
        duo_fb = player["duo_fpp_matches"] and player["duo_fpp_matches"] < MIN_MATCHES_FOR_ADR
        return stats_embed(
            pubg_name=player["pubg_name"],
            squad_adr=player["squad_fpp_adr"],
            squad_tier=player["squad_fpp_tier"],
            squad_matches=player["squad_fpp_matches"] or 0,
            duo_adr=player["duo_fpp_adr"],
            duo_tier=player["duo_fpp_tier"],
            duo_matches=player["duo_fpp_matches"] or 0,
            season=season,
            is_fallback_squad=bool(squad_fb),
            is_fallback_duo=bool(duo_fb),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
