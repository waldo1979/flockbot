import aiosqlite


# --- Feedback ---

async def can_give_feedback(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> bool:
    """Check if 24h has passed since last feedback from this user to target."""
    cursor = await db.execute(
        """SELECT 1 FROM feedback
           WHERE from_user=? AND to_user=?
           AND created_at > datetime('now', '-1 day')""",
        (from_user, to_user),
    )
    return await cursor.fetchone() is None


async def insert_feedback(
    db: aiosqlite.Connection, from_user: str, to_user: str, value: int
) -> None:
    await db.execute(
        "INSERT INTO feedback (from_user, to_user, value) VALUES (?, ?, ?)",
        (from_user, to_user, value),
    )
    await db.commit()


async def get_feedback_between(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> list[dict]:
    cursor = await db.execute(
        "SELECT value, created_at FROM feedback WHERE from_user=? AND to_user=?",
        (from_user, to_user),
    )
    rows = await cursor.fetchall()
    return [{"value": r[0], "created_at": r[1]} for r in rows]


async def get_all_feedback_to(
    db: aiosqlite.Connection, to_user: str
) -> list[dict]:
    cursor = await db.execute(
        "SELECT from_user, value, created_at FROM feedback WHERE to_user=?",
        (to_user,),
    )
    rows = await cursor.fetchall()
    return [{"from_user": r[0], "value": r[1], "created_at": r[2]} for r in rows]


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


# --- Co-play ---

async def record_co_play(
    db: aiosqlite.Connection, player_a: str, player_b: str, date: str
) -> None:
    # Enforce canonical ordering
    a, b = (player_a, player_b) if player_a < player_b else (player_b, player_a)
    await db.execute(
        """INSERT INTO co_play_log (player_a, player_b, date, count)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(player_a, player_b, date)
           DO UPDATE SET count = count + 1""",
        (a, b, date),
    )
    await db.commit()


async def get_co_play_count(
    db: aiosqlite.Connection, user_a: str, user_b: str, since_weeks: int = 8
) -> int:
    a, b = (user_a, user_b) if user_a < user_b else (user_b, user_a)
    cursor = await db.execute(
        """SELECT COALESCE(SUM(count), 0) FROM co_play_log
           WHERE player_a=? AND player_b=?
           AND date >= date('now', ? || ' days')""",
        (a, b, str(-since_weeks * 7)),
    )
    row = await cursor.fetchone()
    return row[0]
