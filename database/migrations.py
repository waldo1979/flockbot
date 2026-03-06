import logging

import aiosqlite

log = logging.getLogger(__name__)

CURRENT_VERSION = 1


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


_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1,
}
