import aiosqlite


async def upsert_player(
    db: aiosqlite.Connection,
    discord_id: str,
    pubg_id: str,
    pubg_name: str,
) -> None:
    await db.execute(
        """INSERT INTO players (discord_id, pubg_id, pubg_name)
           VALUES (?, ?, ?)
           ON CONFLICT(discord_id) DO UPDATE SET pubg_id=?, pubg_name=?""",
        (discord_id, pubg_id, pubg_name, pubg_id, pubg_name),
    )
    await db.commit()


async def get_player(db: aiosqlite.Connection, discord_id: str) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def get_player_by_pubg_id(
    db: aiosqlite.Connection, pubg_id: str
) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM players WHERE pubg_id = ?", (pubg_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def get_player_by_pubg_name(
    db: aiosqlite.Connection, pubg_name: str
) -> dict | None:
    cursor = await db.execute(
        "SELECT * FROM players WHERE pubg_name COLLATE NOCASE = ?", (pubg_name,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def update_cached_stats(
    db: aiosqlite.Connection,
    discord_id: str,
    squad_fpp_adr: float | None,
    squad_fpp_tier: str | None,
    squad_fpp_matches: int,
    duo_fpp_adr: float | None,
    duo_fpp_tier: str | None,
    duo_fpp_matches: int,
    adr_season: str,
) -> None:
    await db.execute(
        """UPDATE players SET
           squad_fpp_adr=?, squad_fpp_tier=?, squad_fpp_matches=?,
           duo_fpp_adr=?, duo_fpp_tier=?, duo_fpp_matches=?,
           adr_season=?, last_stats_update=datetime('now')
           WHERE discord_id=?""",
        (
            squad_fpp_adr, squad_fpp_tier, squad_fpp_matches,
            duo_fpp_adr, duo_fpp_tier, duo_fpp_matches,
            adr_season, discord_id,
        ),
    )
    await db.commit()


async def get_all_players(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute("SELECT * FROM players")
    rows = await cursor.fetchall()
    if not rows:
        return []
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def set_queue_preference(
    db: aiosqlite.Connection, discord_id: str, preference: str
) -> None:
    await db.execute(
        "UPDATE players SET queue_preference = ? WHERE discord_id = ?",
        (preference, discord_id),
    )
    await db.commit()


async def get_leaderboard(
    db: aiosqlite.Connection, mode: str, limit: int = 10
) -> list[dict]:
    if mode == "squad-fpp":
        adr_col, tier_col = "squad_fpp_adr", "squad_fpp_tier"
    else:
        adr_col, tier_col = "duo_fpp_adr", "duo_fpp_tier"

    cursor = await db.execute(
        f"""SELECT pubg_name, {adr_col} as adr, {tier_col} as tier
            FROM players
            WHERE {adr_col} IS NOT NULL
            ORDER BY {adr_col} DESC
            LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]
