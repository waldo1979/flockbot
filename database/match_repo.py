import aiosqlite


async def match_exists(
    db: aiosqlite.Connection, pubg_id: str, match_id: str
) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM match_stats WHERE pubg_id=? AND match_id=?",
        (pubg_id, match_id),
    )
    return await cursor.fetchone() is not None


async def insert_match(
    db: aiosqlite.Connection,
    pubg_id: str,
    match_id: str,
    game_mode: str,
    season: str,
    damage_dealt: float,
    kills: int,
    assists: int,
    win_place: int,
    match_date: str,
) -> None:
    await db.execute(
        """INSERT OR IGNORE INTO match_stats
           (pubg_id, match_id, game_mode, season, damage_dealt,
            kills, assists, win_place, match_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pubg_id, match_id, game_mode, season, damage_dealt,
         kills, assists, win_place, match_date),
    )


async def get_adr_for_mode_season(
    db: aiosqlite.Connection,
    pubg_id: str,
    game_mode: str,
    season: str,
) -> tuple[float | None, int]:
    """Returns (adr, match_count) for a mode+season. ADR is None if no matches."""
    cursor = await db.execute(
        """SELECT SUM(damage_dealt), COUNT(*)
           FROM match_stats
           WHERE pubg_id=? AND game_mode=? AND season=?""",
        (pubg_id, game_mode, season),
    )
    row = await cursor.fetchone()
    total_damage, count = row
    if not count:
        return None, 0
    return total_damage / count, count


async def get_seasons_for_player(
    db: aiosqlite.Connection, pubg_id: str
) -> list[str]:
    """Return distinct seasons for a player, most recent first."""
    cursor = await db.execute(
        """SELECT DISTINCT season FROM match_stats
           WHERE pubg_id=?
           ORDER BY season DESC""",
        (pubg_id,),
    )
    rows = await cursor.fetchall()
    return [r[0] for r in rows]
