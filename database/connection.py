import logging
from pathlib import Path

import aiosqlite

from database.migrations import run_migrations

log = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db(path: str) -> aiosqlite.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    schema = _SCHEMA_PATH.read_text()
    await db.executescript(schema)
    await db.commit()
    await run_migrations(db)
    log.info("Database initialized at %s", path)
    return db


async def close_db(db: aiosqlite.Connection) -> None:
    await db.close()
    log.info("Database connection closed")
