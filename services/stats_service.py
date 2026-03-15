import logging
from dataclasses import dataclass

import aiosqlite

from database import match_repo
from services.pubg_api import PUBGApiClient

log = logging.getLogger(__name__)

MIN_MATCHES_FOR_ADR = 10

TIER_THRESHOLDS = [
    (400, "400+"),
    (300, "300+"),
    (250, "250+"),
    (200, "200+"),
    (100, "100+"),
]


def assign_tier(adr: float) -> str:
    for threshold, label in TIER_THRESHOLDS:
        if adr >= threshold:
            return label
    return "<100"


@dataclass
class ComputedStats:
    squad_fpp_adr: float | None
    squad_fpp_tier: str | None
    squad_fpp_matches: int
    duo_fpp_adr: float | None
    duo_fpp_tier: str | None
    duo_fpp_matches: int
    adr_season: str


async def get_effective_adr(
    db: aiosqlite.Connection,
    pubg_id: str,
    game_mode: str,
    current_season: str,
    previous_season: str | None = None,
) -> tuple[float | None, str | None, int, bool]:
    """Returns (adr, tier, match_count, is_fallback).

    Fallback chain: current season (>=10 matches) -> previous season -> None ("New").
    """
    adr, count = await match_repo.get_adr_for_mode_season(
        db, pubg_id, game_mode, current_season
    )
    if adr is not None and count >= MIN_MATCHES_FOR_ADR:
        return adr, assign_tier(adr), count, False

    # Try previous season
    if previous_season:
        prev_adr, prev_count = await match_repo.get_adr_for_mode_season(
            db, pubg_id, game_mode, previous_season
        )
        if prev_adr is not None and prev_count >= MIN_MATCHES_FOR_ADR:
            return prev_adr, assign_tier(prev_adr), prev_count, True

    # Not enough data
    return None, None, count, False


FPP_MODES = {"squad-fpp", "duo-fpp"}


async def refresh_player_stats(
    db: aiosqlite.Connection,
    api: PUBGApiClient,
    pubg_id: str,
    current_season: str,
    previous_season: str | None = None,
) -> ComputedStats | None:
    """Fetch recent matches from PUBG API, store FPP matches, compute ADR.

    Returns ComputedStats for the caller to persist (players or player_cache).
    Returns None if match fetch fails.
    """
    # Get recent match IDs
    match_ids = await api.get_player_match_ids(pubg_id)
    if not match_ids:
        log.debug("No matches found for %s", pubg_id)
        # Still compute stats from existing data
        return await _compute_stats(db, pubg_id, current_season, previous_season)

    new_matches = 0
    for match_id in match_ids:
        if await match_repo.match_exists(db, pubg_id, match_id):
            continue

        match_data = await api.get_match(match_id)
        if not match_data:
            continue

        # Only store FPP modes
        if match_data.game_mode not in FPP_MODES:
            continue

        # Find this player's participant entry
        participant = None
        for p in match_data.participants:
            if p.player_id == pubg_id:
                participant = p
                break

        if not participant:
            continue

        await match_repo.insert_match(
            db,
            pubg_id=pubg_id,
            match_id=match_data.match_id,
            game_mode=match_data.game_mode,
            season=current_season,
            damage_dealt=participant.damage_dealt,
            kills=participant.kills,
            assists=participant.assists,
            win_place=participant.win_place,
            match_date=match_data.created_at,
        )
        new_matches += 1

    await db.commit()

    if new_matches:
        log.info("Stored %d new matches for %s", new_matches, pubg_id)

    return await _compute_stats(db, pubg_id, current_season, previous_season)


async def _compute_stats(
    db: aiosqlite.Connection,
    pubg_id: str,
    current_season: str,
    previous_season: str | None,
) -> ComputedStats:
    squad_adr, squad_tier, squad_count, _ = await get_effective_adr(
        db, pubg_id, "squad-fpp", current_season, previous_season
    )
    duo_adr, duo_tier, duo_count, _ = await get_effective_adr(
        db, pubg_id, "duo-fpp", current_season, previous_season
    )
    return ComputedStats(
        squad_fpp_adr=squad_adr,
        squad_fpp_tier=squad_tier,
        squad_fpp_matches=squad_count,
        duo_fpp_adr=duo_adr,
        duo_fpp_tier=duo_tier,
        duo_fpp_matches=duo_count,
        adr_season=current_season,
    )
