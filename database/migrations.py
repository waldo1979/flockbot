import logging

import aiosqlite

log = logging.getLogger(__name__)

CURRENT_VERSION = 4


async def get_schema_version(db: aiosqlite.Connection) -> int:
    async with db.execute(
        "SELECT MAX(version) FROM schema_version"
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row[0] is not None else 0


async def set_schema_version(db: aiosqlite.Connection, version: int) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
        (version,),
    )
    await db.commit()


async def run_migrations(db: aiosqlite.Connection) -> None:
    current = await get_schema_version(db)
    if current >= CURRENT_VERSION:
        log.info("Schema up to date (version %d)", current)
        return

    for version in range(current + 1, CURRENT_VERSION + 1):
        migrate_fn = _MIGRATIONS.get(version)
        if migrate_fn is None:
            raise RuntimeError(f"Missing migration for version {version}")
        log.info("Applying migration %d", version)
        await migrate_fn(db)
        await set_schema_version(db, version)

    log.info("Migrations complete (now at version %d)", CURRENT_VERSION)


async def _migrate_v1(db: aiosqlite.Connection) -> None:
    """Initial schema — tables created by schema.sql, just stamp the version."""
    pass


async def _migrate_v2(db: aiosqlite.Connection) -> None:
    """Add queue_preference column to players table."""
    await db.execute(
        "ALTER TABLE players ADD COLUMN queue_preference TEXT DEFAULT 'skill'"
    )
    await db.commit()


async def _migrate_v3(db: aiosqlite.Connection) -> None:
    """Replace feedback + co_play_log with hangout_time table."""
    await db.execute("DROP TABLE IF EXISTS feedback")
    await db.execute("DROP TABLE IF EXISTS co_play_log")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS hangout_time (
            player_a     TEXT NOT NULL,
            player_b     TEXT NOT NULL,
            minutes      REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(player_a, player_b),
            CHECK(player_a < player_b)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_hangout_time
            ON hangout_time(player_a, player_b)
    """)
    await db.commit()


async def _migrate_v4(db: aiosqlite.Connection) -> None:
    """Add player_cache table and migrate match_stats from discord_id to pubg_id."""
    # Create player_cache table
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_cache (
            pubg_id           TEXT PRIMARY KEY,
            pubg_name         TEXT NOT NULL,
            last_lookup       TEXT NOT NULL DEFAULT (datetime('now')),
            last_stats_update TEXT,
            squad_fpp_adr     REAL,
            squad_fpp_tier    TEXT,
            squad_fpp_matches INTEGER DEFAULT 0,
            duo_fpp_adr       REAL,
            duo_fpp_tier      TEXT,
            duo_fpp_matches   INTEGER DEFAULT 0,
            adr_season        TEXT
        )
    """)

    # Recreate match_stats with pubg_id instead of discord_id
    await db.execute("""
        CREATE TABLE IF NOT EXISTS match_stats_new (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            pubg_id      TEXT NOT NULL,
            match_id     TEXT NOT NULL,
            game_mode    TEXT NOT NULL CHECK(game_mode IN ('squad-fpp', 'duo-fpp')),
            season       TEXT NOT NULL,
            damage_dealt REAL NOT NULL,
            kills        INTEGER NOT NULL,
            assists      INTEGER NOT NULL,
            win_place    INTEGER NOT NULL,
            match_date   TEXT NOT NULL,
            fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(pubg_id, match_id)
        )
    """)

    # Backfill: join old match_stats with players to get pubg_id
    await db.execute("""
        INSERT OR IGNORE INTO match_stats_new
            (pubg_id, match_id, game_mode, season, damage_dealt,
             kills, assists, win_place, match_date, fetched_at)
        SELECT p.pubg_id, ms.match_id, ms.game_mode, ms.season, ms.damage_dealt,
               ms.kills, ms.assists, ms.win_place, ms.match_date, ms.fetched_at
        FROM match_stats ms
        JOIN players p ON ms.discord_id = p.discord_id
        WHERE p.pubg_id IS NOT NULL
    """)

    await db.execute("DROP TABLE match_stats")
    await db.execute("ALTER TABLE match_stats_new RENAME TO match_stats")
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_match_stats_player_mode
            ON match_stats(pubg_id, game_mode, season)
    """)
    await db.commit()


_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1,
    2: _migrate_v2,
    3: _migrate_v3,
    4: _migrate_v4,
}
