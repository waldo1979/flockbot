import aiosqlite


# --- Hangout Time ---

async def upsert_hangout_time(
    db: aiosqlite.Connection, player_a: str, player_b: str, additional_minutes: float
) -> None:
    """Add minutes to a pair's hangout total. Enforces canonical ordering."""
    a, b = (player_a, player_b) if player_a < player_b else (player_b, player_a)
    await db.execute(
        """INSERT INTO hangout_time (player_a, player_b, minutes, last_updated)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(player_a, player_b)
           DO UPDATE SET minutes = minutes + ?, last_updated = datetime('now')""",
        (a, b, additional_minutes, additional_minutes),
    )
    await db.commit()


async def get_hangout_minutes(
    db: aiosqlite.Connection, user_a: str, user_b: str
) -> tuple[float, str | None]:
    """Return (total_minutes, last_updated) for a pair. Returns (0.0, None) if no row."""
    a, b = (user_a, user_b) if user_a < user_b else (user_b, user_a)
    cursor = await db.execute(
        "SELECT minutes, last_updated FROM hangout_time WHERE player_a = ? AND player_b = ?",
        (a, b),
    )
    row = await cursor.fetchone()
    if not row:
        return 0.0, None
    return row[0], row[1]


# --- Blocks ---

async def insert_block(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO blocks (from_user, to_user) VALUES (?, ?)",
        (from_user, to_user),
    )
    await db.commit()


async def remove_block(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> bool:
    cursor = await db.execute(
        "DELETE FROM blocks WHERE from_user=? AND to_user=?",
        (from_user, to_user),
    )
    await db.commit()
    return cursor.rowcount > 0


async def is_blocked(
    db: aiosqlite.Connection, user_a: str, user_b: str
) -> bool:
    cursor = await db.execute(
        """SELECT 1 FROM blocks
           WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)""",
        (user_a, user_b, user_b, user_a),
    )
    return await cursor.fetchone() is not None


# --- Buddies ---

async def insert_buddy_request(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> bool:
    """Insert a buddy request. Returns True if mutual (now confirmed)."""
    await db.execute(
        "INSERT OR REPLACE INTO buddies (from_user, to_user, confirmed) VALUES (?, ?, 0)",
        (from_user, to_user),
    )
    # Check if reverse exists
    cursor = await db.execute(
        "SELECT 1 FROM buddies WHERE from_user=? AND to_user=?",
        (to_user, from_user),
    )
    mutual = await cursor.fetchone() is not None

    if mutual:
        await db.execute(
            "UPDATE buddies SET confirmed=1 WHERE from_user=? AND to_user=?",
            (from_user, to_user),
        )
        await db.execute(
            "UPDATE buddies SET confirmed=1 WHERE from_user=? AND to_user=?",
            (to_user, from_user),
        )

    await db.commit()
    return mutual


async def are_buddies(
    db: aiosqlite.Connection, user_a: str, user_b: str
) -> bool:
    cursor = await db.execute(
        """SELECT 1 FROM buddies
           WHERE from_user=? AND to_user=? AND confirmed=1""",
        (user_a, user_b),
    )
    return await cursor.fetchone() is not None


async def get_confirmed_buddies(
    db: aiosqlite.Connection, discord_id: str
) -> list[str]:
    cursor = await db.execute(
        "SELECT to_user FROM buddies WHERE from_user=? AND confirmed=1",
        (discord_id,),
    )
    rows = await cursor.fetchall()
    return [r[0] for r in rows]
