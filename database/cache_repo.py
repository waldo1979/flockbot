import aiosqlite


async def upsert_cached_player(
    db: aiosqlite.Connection, pubg_id: str, pubg_name: str
) -> None:
    await db.execute(
        """INSERT INTO player_cache (pubg_id, pubg_name, last_lookup)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(pubg_id) DO UPDATE SET
               pubg_name=excluded.pubg_name,
               last_lookup=datetime('now')""",
        (pubg_id, pubg_name),
    )
    await db.commit()


async def get_cached_player_by_name(
    db: aiosqlite.Connection, pubg_name: str
) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM player_cache WHERE pubg_name COLLATE NOCASE = ?",
        (pubg_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def get_cached_player(
    db: aiosqlite.Connection, pubg_id: str
) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM player_cache WHERE pubg_id = ?", (pubg_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def update_cached_stats(
    db: aiosqlite.Connection,
    pubg_id: str,
    squad_fpp_adr: float | None,
    squad_fpp_tier: str | None,
    squad_fpp_matches: int,
    duo_fpp_adr: float | None,
    duo_fpp_tier: str | None,
    duo_fpp_matches: int,
    adr_season: str,
) -> None:
    await db.execute(
        """UPDATE player_cache SET
           squad_fpp_adr=?, squad_fpp_tier=?, squad_fpp_matches=?,
           duo_fpp_adr=?, duo_fpp_tier=?, duo_fpp_matches=?,
           adr_season=?, last_stats_update=datetime('now')
           WHERE pubg_id=?""",
        (
            squad_fpp_adr, squad_fpp_tier, squad_fpp_matches,
            duo_fpp_adr, duo_fpp_tier, duo_fpp_matches,
            adr_season, pubg_id,
        ),
    )
    await db.commit()


async def touch_lookup(db: aiosqlite.Connection, pubg_id: str) -> None:
    await db.execute(
        "UPDATE player_cache SET last_lookup=datetime('now') WHERE pubg_id=?",
        (pubg_id,),
    )
    await db.commit()


async def get_active_cached_players(
    db: aiosqlite.Connection, days: int = 14
) -> list[dict]:
    cursor = await db.execute(
        """SELECT * FROM player_cache
           WHERE last_lookup >= datetime('now', ? || ' days')""",
        (f"-{days}",),
    )
    rows = await cursor.fetchall()
    if not rows:
        return []
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def delete_stale_cached_players(
    db: aiosqlite.Connection, days: int = 30
) -> int:
    cursor = await db.execute(
        """DELETE FROM player_cache
           WHERE last_lookup < datetime('now', ? || ' days')""",
        (f"-{days}",),
    )
    deleted = cursor.rowcount
    await db.commit()
    return deleted


async def delete_cached_player(
    db: aiosqlite.Connection, pubg_id: str
) -> None:
    await db.execute(
        "DELETE FROM player_cache WHERE pubg_id = ?", (pubg_id,)
    )
    await db.commit()
