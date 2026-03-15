import pytest

from database import match_repo, player_repo
from services.stats_service import assign_tier, get_effective_adr


@pytest.fixture
async def seeded_db(db):
    await player_repo.upsert_player(db, "111", "pubg_111", "TestPlayer")
    # Insert 12 squad-fpp matches in current season
    for i in range(12):
        await match_repo.insert_match(
            db,
            pubg_id="pubg_111",
            match_id=f"match_squad_{i}",
            game_mode="squad-fpp",
            season="season_current",
            damage_dealt=200.0 + i * 10,
            kills=2,
            assists=1,
            win_place=5,
            match_date=f"2026-03-0{min(i+1, 9)}T12:00:00Z",
        )
    # Insert 5 duo-fpp matches in current season (below threshold)
    for i in range(5):
        await match_repo.insert_match(
            db,
            pubg_id="pubg_111",
            match_id=f"match_duo_{i}",
            game_mode="duo-fpp",
            season="season_current",
            damage_dealt=300.0,
            kills=3,
            assists=0,
            win_place=2,
            match_date=f"2026-03-0{i+1}T12:00:00Z",
        )
    # Insert 15 duo-fpp matches in previous season
    for i in range(15):
        await match_repo.insert_match(
            db,
            pubg_id="pubg_111",
            match_id=f"match_duo_prev_{i}",
            game_mode="duo-fpp",
            season="season_prev",
            damage_dealt=250.0,
            kills=2,
            assists=1,
            win_place=3,
            match_date=f"2026-01-0{min(i+1, 9)}T12:00:00Z",
        )
    await db.commit()
    return db


class TestAssignTier:
    def test_below_100(self):
        assert assign_tier(50) == "<100"

    def test_100_plus(self):
        assert assign_tier(100) == "100+"
        assert assign_tier(199) == "100+"

    def test_200_plus(self):
        assert assign_tier(200) == "200+"
        assert assign_tier(249) == "200+"

    def test_250_plus(self):
        assert assign_tier(250) == "250+"
        assert assign_tier(299) == "250+"

    def test_300_plus(self):
        assert assign_tier(300) == "300+"
        assert assign_tier(399) == "300+"

    def test_400_plus(self):
        assert assign_tier(400) == "400+"
        assert assign_tier(999) == "400+"

    def test_boundary_exact(self):
        assert assign_tier(0) == "<100"
        assert assign_tier(99) == "<100"
        assert assign_tier(100) == "100+"


class TestGetEffectiveADR:
    async def test_current_season_enough_matches(self, seeded_db):
        adr, tier, count, fallback = await get_effective_adr(
            seeded_db, "pubg_111", "squad-fpp", "season_current", "season_prev"
        )
        assert adr is not None
        assert count == 12
        assert fallback is False
        # damage: 200, 210, 220, ..., 310 -> avg = 255
        assert 254 < adr < 256

    async def test_fallback_to_previous_season(self, seeded_db):
        adr, tier, count, fallback = await get_effective_adr(
            seeded_db, "pubg_111", "duo-fpp", "season_current", "season_prev"
        )
        # Current season has only 5 matches (< 10), should fall back
        assert adr == 250.0
        assert count == 15
        assert fallback is True

    async def test_new_player_no_data(self, seeded_db):
        adr, tier, count, fallback = await get_effective_adr(
            seeded_db, "pubg_111", "squad-fpp", "season_nonexistent"
        )
        assert adr is None
        assert tier is None
        assert count == 0

    async def test_no_fallback_season(self, seeded_db):
        adr, tier, count, fallback = await get_effective_adr(
            seeded_db, "pubg_111", "duo-fpp", "season_current"
        )
        # Only 5 matches, no previous season given
        assert adr is None
        assert tier is None
