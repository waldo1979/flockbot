import aiosqlite

from database import feedback_repo
from utils.time_helpers import weeks_since

# 10 hours of (decayed) hangout time for maximum compatibility signal
HANGOUT_NORMALIZER = 600
# Hangout time half-life: 4 weeks
HANGOUT_HALF_LIFE_WEEKS = 4.0


async def record_block(db: aiosqlite.Connection, from_user: str, to_user: str) -> None:
    await feedback_repo.insert_block(db, from_user, to_user)


async def remove_block(db: aiosqlite.Connection, from_user: str, to_user: str) -> bool:
    return await feedback_repo.remove_block(db, from_user, to_user)


async def record_buddy_request(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> bool:
    """Returns True if buddy bond is now mutual/confirmed."""
    return await feedback_repo.insert_buddy_request(db, from_user, to_user)


async def is_blocked(db: aiosqlite.Connection, user_a: str, user_b: str) -> bool:
    return await feedback_repo.is_blocked(db, user_a, user_b)


async def are_buddies(db: aiosqlite.Connection, user_a: str, user_b: str) -> bool:
    return await feedback_repo.are_buddies(db, user_a, user_b)


async def get_pairwise_compatibility(
    db: aiosqlite.Connection, user_a: str, user_b: str
) -> float:
    """Compatibility score based on shared voice hangout time. Range: 0.0 to 1.0."""
    minutes, last_updated = await feedback_repo.get_hangout_minutes(db, user_a, user_b)
    if minutes == 0.0 or last_updated is None:
        return 0.0

    weeks_age = weeks_since(last_updated)
    decay = 0.5 ** (weeks_age / HANGOUT_HALF_LIFE_WEEKS)

    effective_minutes = minutes * decay
    return min(effective_minutes / HANGOUT_NORMALIZER, 1.0)
