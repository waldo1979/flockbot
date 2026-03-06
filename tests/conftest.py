from pathlib import Path

import aiosqlite
import pytest


SCHEMA_PATH = Path(__file__).parent.parent / "database" / "schema.sql"


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("PRAGMA foreign_keys=ON")
    schema = SCHEMA_PATH.read_text()
    await conn.executescript(schema)
    await conn.commit()
    yield conn
    await conn.close()
