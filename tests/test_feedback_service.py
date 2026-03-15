import pytest

from database import feedback_repo, player_repo
from services.feedback_service import (
    record_block,
    remove_block,
    is_blocked,
    record_buddy_request,
    are_buddies,
    get_pairwise_compatibility,
)


@pytest.fixture
async def users(db):
    await player_repo.upsert_player(db, "A", "pubg_A", "PlayerA")
    await player_repo.upsert_player(db, "B", "pubg_B", "PlayerB")
    await player_repo.upsert_player(db, "C", "pubg_C", "PlayerC")
    return db


class TestBlocks:
    async def test_block_and_check(self, users):
        assert not await is_blocked(users, "A", "B")
        await record_block(users, "A", "B")
        assert await is_blocked(users, "A", "B")
        # Reverse direction also blocked
        assert await is_blocked(users, "B", "A")

    async def test_remove_block(self, users):
        await record_block(users, "A", "B")
        removed = await remove_block(users, "A", "B")
        assert removed is True
        assert not await is_blocked(users, "A", "B")

    async def test_remove_nonexistent(self, users):
        removed = await remove_block(users, "A", "B")
        assert removed is False


class TestBuddies:
    async def test_one_sided_not_confirmed(self, users):
        mutual = await record_buddy_request(users, "A", "B")
        assert mutual is False
        assert not await are_buddies(users, "A", "B")

    async def test_mutual_confirms(self, users):
        await record_buddy_request(users, "A", "B")
        mutual = await record_buddy_request(users, "B", "A")
        assert mutual is True
        assert await are_buddies(users, "A", "B")
        assert await are_buddies(users, "B", "A")

    async def test_get_confirmed_buddies(self, users):
        await record_buddy_request(users, "A", "B")
        await record_buddy_request(users, "B", "A")
        buddies = await feedback_repo.get_confirmed_buddies(users, "A")
        assert "B" in buddies


class TestHangoutCompatibility:
    async def test_no_hangout_returns_zero(self, users):
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score == 0.0

    async def test_hangout_produces_positive_score(self, users):
        await feedback_repo.upsert_hangout_time(users, "A", "B", 60.0)
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score > 0.0

    async def test_hangout_score_capped_at_one(self, users):
        await feedback_repo.upsert_hangout_time(users, "A", "B", 10000.0)
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score <= 1.0

    async def test_canonical_ordering(self, users):
        """Pair (B, A) should return same score as (A, B)."""
        await feedback_repo.upsert_hangout_time(users, "B", "A", 120.0)
        score_ab = await get_pairwise_compatibility(users, "A", "B")
        score_ba = await get_pairwise_compatibility(users, "B", "A")
        assert abs(score_ab - score_ba) < 0.001
        assert score_ab > 0.0

    async def test_hangout_accumulates(self, users):
        await feedback_repo.upsert_hangout_time(users, "A", "B", 30.0)
        await feedback_repo.upsert_hangout_time(users, "A", "B", 30.0)
        minutes, _ = await feedback_repo.get_hangout_minutes(users, "A", "B")
        assert minutes == 60.0


class TestPairwiseCompatibility:
    async def test_no_data_returns_zero(self, users):
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score == 0.0
