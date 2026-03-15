import pytest

from database import cache_repo


class TestCacheRepo:
    async def test_upsert_and_get_by_name(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "TestPlayer")
        result = await cache_repo.get_cached_player_by_name(db, "TestPlayer")
        assert result is not None
        assert result["pubg_id"] == "pubg_abc"
        assert result["pubg_name"] == "TestPlayer"

    async def test_get_by_name_case_insensitive(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "TestPlayer")
        result = await cache_repo.get_cached_player_by_name(db, "testplayer")
        assert result is not None
        assert result["pubg_id"] == "pubg_abc"

    async def test_get_cached_player(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "TestPlayer")
        result = await cache_repo.get_cached_player(db, "pubg_abc")
        assert result is not None
        assert result["pubg_name"] == "TestPlayer"

    async def test_get_nonexistent_returns_none(self, db):
        result = await cache_repo.get_cached_player(db, "nonexistent")
        assert result is None

    async def test_upsert_updates_name(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "OldName")
        await cache_repo.upsert_cached_player(db, "pubg_abc", "NewName")
        result = await cache_repo.get_cached_player(db, "pubg_abc")
        assert result["pubg_name"] == "NewName"

    async def test_update_cached_stats(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "TestPlayer")
        await cache_repo.update_cached_stats(
            db,
            pubg_id="pubg_abc",
            squad_fpp_adr=250.0,
            squad_fpp_tier="250+",
            squad_fpp_matches=15,
            duo_fpp_adr=180.0,
            duo_fpp_tier="100+",
            duo_fpp_matches=12,
            adr_season="season_1",
        )
        result = await cache_repo.get_cached_player(db, "pubg_abc")
        assert result["squad_fpp_adr"] == 250.0
        assert result["squad_fpp_tier"] == "250+"
        assert result["squad_fpp_matches"] == 15
        assert result["duo_fpp_adr"] == 180.0
        assert result["adr_season"] == "season_1"

    async def test_get_active_cached_players(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_1", "Player1")
        await cache_repo.upsert_cached_player(db, "pubg_2", "Player2")
        active = await cache_repo.get_active_cached_players(db, days=14)
        assert len(active) == 2

    async def test_delete_stale_cached_players(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_1", "Player1")
        # Manually backdate the lookup
        await db.execute(
            "UPDATE player_cache SET last_lookup = datetime('now', '-31 days') "
            "WHERE pubg_id = 'pubg_1'"
        )
        await db.commit()
        deleted = await cache_repo.delete_stale_cached_players(db, days=30)
        assert deleted == 1
        result = await cache_repo.get_cached_player(db, "pubg_1")
        assert result is None

    async def test_delete_stale_keeps_recent(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_1", "Player1")
        deleted = await cache_repo.delete_stale_cached_players(db, days=30)
        assert deleted == 0
        result = await cache_repo.get_cached_player(db, "pubg_1")
        assert result is not None

    async def test_delete_cached_player(self, db):
        await cache_repo.upsert_cached_player(db, "pubg_abc", "TestPlayer")
        await cache_repo.delete_cached_player(db, "pubg_abc")
        result = await cache_repo.get_cached_player(db, "pubg_abc")
        assert result is None
