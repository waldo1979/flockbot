import pytest

from database import feedback_repo, player_repo
from services.feedback_service import (
    record_feedback,
    record_block,
    remove_block,
    is_blocked,
    record_buddy_request,
    are_buddies,
    get_weighted_score,
    get_pairwise_compatibility,
)


@pytest.fixture
async def users(db):
    await player_repo.upsert_player(db, "A", "pubg_A", "PlayerA")
    await player_repo.upsert_player(db, "B", "pubg_B", "PlayerB")
    await player_repo.upsert_player(db, "C", "pubg_C", "PlayerC")
    return db


class TestRecordFeedback:
    async def test_positive_feedback(self, users):
        err = await record_feedback(users, "A", "B", 1)
        assert err is None

    async def test_self_feedback_rejected(self, users):
        err = await record_feedback(users, "A", "A", 1)
        assert err is not None
        assert "yourself" in err.lower()

    async def test_duplicate_within_24h(self, users):
        await record_feedback(users, "A", "B", 1)
        err = await record_feedback(users, "A", "B", -1)
        assert err is not None
        assert "24 hours" in err


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


class TestWeightedScore:
    async def test_no_feedback_returns_none(self, users):
        score = await get_weighted_score(users, "A", "B")
        assert score is None

    async def test_positive_feedback(self, users):
        await feedback_repo.insert_feedback(users, "A", "B", 1)
        score = await get_weighted_score(users, "A", "B")
        assert score is not None
        assert score > 0

    async def test_negative_feedback(self, users):
        await feedback_repo.insert_feedback(users, "A", "B", -1)
        score = await get_weighted_score(users, "A", "B")
        assert score is not None
        assert score < 0


class TestPairwiseCompatibility:
    async def test_no_data_returns_zero(self, users):
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score == 0.0

    async def test_negative_dominates(self, users):
        await feedback_repo.insert_feedback(users, "A", "B", -1)
        # Add co-play to try to override
        await feedback_repo.record_co_play(users, "A", "B", "2026-03-01")
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score < 0  # Negative feedback dominates

    async def test_positive_with_co_play(self, users):
        await feedback_repo.insert_feedback(users, "A", "B", 1)
        for i in range(5):
            await feedback_repo.record_co_play(users, "A", "B", f"2026-03-0{i+1}")
        score = await get_pairwise_compatibility(users, "A", "B")
        assert score > 0
