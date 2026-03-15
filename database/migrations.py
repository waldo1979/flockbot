import logging

import aiosqlite

log = logging.getLogger(__name__)

CURRENT_VERSION = 3


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


_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1,
    2: _migrate_v2,
    3: _migrate_v3,
}
