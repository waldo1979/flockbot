import aiosqlite

from database import feedback_repo
from utils.time_helpers import decay_weight, weeks_since

FEEDBACK_MAX_AGE_DAYS = 84
CO_PLAY_NORMALIZER = 10


async def record_feedback(
    db: aiosqlite.Connection, from_user: str, to_user: str, value: int
) -> str | None:
    """Record feedback. Returns error message string or None on success."""
    if from_user == to_user:
        return "You cannot rate yourself."
    if not await feedback_repo.can_give_feedback(db, from_user, to_user):
        return "You already gave feedback to this player in the last 24 hours."
    await feedback_repo.insert_feedback(db, from_user, to_user, value)
    return None


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


async def get_weighted_score(
    db: aiosqlite.Connection, from_user: str, to_user: str
) -> float | None:
    """Decay-weighted feedback score from one user to another. Returns None if no feedback."""
    entries = await feedback_repo.get_feedback_between(db, from_user, to_user)
    if not entries:
        return None

    total = 0.0
    weight_sum = 0.0
    for entry in entries:
        w = decay_weight(weeks_since(entry["created_at"]))
        if w > 0:
            total += entry["value"] * w
            weight_sum += w

    if weight_sum == 0:
        return None
    return total / weight_sum


async def get_pairwise_compatibility(
    db: aiosqlite.Connection, user_a: str, user_b: str
) -> float:
    """Composite compatibility score between two players. Range roughly -1.0 to +1.0."""
    score_a_to_b = await get_weighted_score(db, user_a, user_b)
    score_b_to_a = await get_weighted_score(db, user_b, user_a)

    if score_a_to_b is not None and score_b_to_a is not None:
        direct = (score_a_to_b + score_b_to_a) / 2
    elif score_a_to_b is not None:
        direct = score_a_to_b
    elif score_b_to_a is not None:
        direct = score_b_to_a
    else:
        direct = 0.0

    co_play_count = await feedback_repo.get_co_play_count(db, user_a, user_b)
    co_play_signal = min(co_play_count / CO_PLAY_NORMALIZER, 1.0)

    # Negative feedback dominates — co-play cannot override it
    if direct < 0:
        return direct
    return 0.7 * direct + 0.3 * co_play_signal
