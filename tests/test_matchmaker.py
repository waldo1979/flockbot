import pytest
from datetime import datetime, timezone, timedelta

from database import feedback_repo, player_repo
from services.matchmaker import (
    QueuedPlayer, QueuePreference, form_squads, form_duos,
    _relaxation_factor, _effective_wait_secs, _total_score, _skill_score,
    RELAXATION_START_SECS, RELAXATION_FULL_SECS,
)


def _p(name: str, adr: float, wait_minutes: float = 0.0,
       preference: QueuePreference = QueuePreference.SKILL) -> QueuedPlayer:
    join_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(minutes=wait_minutes)
    return QueuedPlayer(
        discord_id=name, pubg_name=name, adr=adr,
        join_time=join_time, preference=preference,
    )


# Fixed "now" for tests
NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
async def match_db(db):
    for name in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        await player_repo.upsert_player(db, name, f"pubg_{name}", name)
    return db


class TestFormDuos:
    async def test_basic_duo(self, match_db):
        players = [_p("A", 200), _p("B", 210)]
        groups = await form_duos(match_db, players, now=NOW)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    async def test_not_enough_players(self, match_db):
        players = [_p("A", 200)]
        groups = await form_duos(match_db, players, now=NOW)
        assert groups == []

    async def test_four_players_two_duos(self, match_db):
        players = [_p("A", 100), _p("B", 110), _p("C", 300), _p("D", 310)]
        groups = await form_duos(match_db, players, now=NOW)
        assert len(groups) == 2
        # Similar ADR players should be grouped
        for group in groups:
            adrs = [p.adr for p in group]
            assert abs(adrs[0] - adrs[1]) <= 220  # Not the worst combo

    async def test_blocked_players_not_paired(self, match_db):
        await feedback_repo.insert_block(match_db, "A", "B")
        players = [_p("A", 200), _p("B", 200), _p("C", 200), _p("D", 200)]
        groups = await form_duos(match_db, players, now=NOW)
        for group in groups:
            ids = {p.discord_id for p in group}
            assert not ({"A", "B"} <= ids)


class TestFormSquads:
    async def test_basic_squad(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220), _p("D", 230)]
        groups = await form_squads(match_db, players, now=NOW)
        assert len(groups) == 1
        assert len(groups[0]) == 4

    async def test_not_enough_players(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220)]
        groups = await form_squads(match_db, players, now=NOW)
        assert groups == []

    async def test_five_players_one_squad(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220), _p("D", 230), _p("E", 240)]
        groups = await form_squads(match_db, players, now=NOW)
        assert len(groups) == 1
        assert len(groups[0]) == 4

    async def test_eight_players_two_squads(self, match_db):
        players = [
            _p("A", 100), _p("B", 110), _p("C", 120), _p("D", 130),
            _p("E", 300), _p("F", 310), _p("G", 320), _p("H", 330),
        ]
        groups = await form_squads(match_db, players, now=NOW)
        assert len(groups) == 2

    async def test_blocked_players_separated(self, match_db):
        await feedback_repo.insert_block(match_db, "A", "B")
        players = [_p("A", 200), _p("B", 200), _p("C", 200), _p("D", 200), _p("E", 200)]
        groups = await form_squads(match_db, players, now=NOW)
        for group in groups:
            ids = {p.discord_id for p in group}
            assert not ({"A", "B"} <= ids)

    async def test_buddies_grouped_together(self, match_db):
        await feedback_repo.insert_buddy_request(match_db, "A", "B")
        await feedback_repo.insert_buddy_request(match_db, "B", "A")
        players = [_p("A", 100), _p("B", 100), _p("C", 400), _p("D", 400), _p("E", 400), _p("F", 400)]
        groups = await form_squads(match_db, players, now=NOW)
        # A and B should be in the same group despite ADR mismatch
        for group in groups:
            ids = {p.discord_id for p in group}
            if "A" in ids:
                assert "B" in ids
            if "B" in ids:
                assert "A" in ids

    async def test_skill_similarity_preferred(self, match_db):
        players = [_p("A", 100), _p("B", 110), _p("C", 400), _p("D", 410)]
        groups = await form_squads(match_db, players, now=NOW)
        # With only 4 players, they must be grouped together
        assert len(groups) == 1

    async def test_empty_pool(self, match_db):
        groups = await form_squads(match_db, [], now=NOW)
        assert groups == []


class TestRelaxationFactor:
    def test_zero_when_fresh(self):
        """Players waiting < 2 min get relaxation factor 0.0."""
        group = [_p("A", 200, wait_minutes=1.0), _p("B", 300, wait_minutes=0.5)]
        r = _relaxation_factor(group, NOW)
        assert r == 0.0

    def test_one_at_five_minutes(self):
        """Players waiting >= 5 min get relaxation factor 1.0."""
        group = [_p("A", 200, wait_minutes=5.0), _p("B", 300, wait_minutes=3.0)]
        r = _relaxation_factor(group, NOW)
        assert r == 1.0

    def test_linear_midpoint(self):
        """At 3.5 min wait, relaxation should be ~0.5 (linear between 2-5 min)."""
        group = [_p("A", 200, wait_minutes=3.5), _p("B", 300, wait_minutes=1.0)]
        r = _relaxation_factor(group, NOW)
        # 3.5 min = 210 sec. (210 - 120) / (300 - 120) = 90/180 = 0.5
        assert abs(r - 0.5) < 0.01

    def test_fast_preference_doubles_effective_wait(self):
        """FAST preference at 1.5 min raw → effective 3 min → relaxation > 0."""
        group = [_p("A", 200, wait_minutes=1.5, preference=QueuePreference.FAST)]
        r = _relaxation_factor(group, NOW)
        # Effective wait: 1.5 * 2 = 3 min = 180 sec. (180 - 120) / (300 - 120) = 60/180 ≈ 0.333
        assert r > 0.0
        assert abs(r - 1 / 3) < 0.01


class TestScoringWithRelaxation:
    async def test_scoring_unchanged_with_no_relaxation(self, match_db):
        """Fresh players (< 2 min) get the original 0.6*skill + 0.4*social formula."""
        group = [_p("A", 200, wait_minutes=0.0), _p("B", 210, wait_minutes=0.0)]
        score = await _total_score(match_db, group, NOW)

        # Compute expected: skill = 1.0 - 10/400 = 0.975, social = 0.0 (no feedback)
        # total = 0.6 * 0.975 + 0.4 * 0.0 = 0.585
        expected = 0.6 * (1.0 - 10 / 400) + 0.4 * 0.0
        assert abs(score - expected) < 0.001

    async def test_scoring_ignores_skill_at_full_relaxation(self, match_db):
        """At full relaxation (5+ min), wide ADR gap doesn't hurt the score."""
        # Two players with huge ADR gap, both waiting 6 minutes
        group_wide = [_p("A", 100, wait_minutes=6.0), _p("B", 500, wait_minutes=6.0)]
        group_tight = [_p("C", 200, wait_minutes=6.0), _p("D", 210, wait_minutes=6.0)]

        score_wide = await _total_score(match_db, group_wide, NOW)
        score_tight = await _total_score(match_db, group_tight, NOW)

        # At r=1.0: score = 0.4*social + 0.6 baseline. Social is 0 for both (no feedback).
        # So both should score 0.6 regardless of ADR gap.
        assert abs(score_wide - 0.6) < 0.001
        assert abs(score_tight - 0.6) < 0.001
        assert abs(score_wide - score_tight) < 0.001

    async def test_blocks_enforced_at_full_relaxation(self, match_db):
        """Blocks are never relaxed — blocked players can't be matched even after 5+ min."""
        await feedback_repo.insert_block(match_db, "A", "B")
        players = [
            _p("A", 200, wait_minutes=10.0),
            _p("B", 200, wait_minutes=10.0),
            _p("C", 200, wait_minutes=10.0),
            _p("D", 200, wait_minutes=10.0),
            _p("E", 200, wait_minutes=10.0),
        ]
        groups = await form_squads(match_db, players, now=NOW)
        for group in groups:
            ids = {p.discord_id for p in group}
            assert not ({"A", "B"} <= ids)

    async def test_buddies_enforced_at_full_relaxation(self, match_db):
        """Buddy pairs stay together even at full relaxation."""
        await feedback_repo.insert_buddy_request(match_db, "A", "B")
        await feedback_repo.insert_buddy_request(match_db, "B", "A")
        players = [
            _p("A", 100, wait_minutes=10.0),
            _p("B", 100, wait_minutes=10.0),
            _p("C", 400, wait_minutes=10.0),
            _p("D", 400, wait_minutes=10.0),
            _p("E", 400, wait_minutes=10.0),
            _p("F", 400, wait_minutes=10.0),
        ]
        groups = await form_squads(match_db, players, now=NOW)
        for group in groups:
            ids = {p.discord_id for p in group}
            if "A" in ids:
                assert "B" in ids
            if "B" in ids:
                assert "A" in ids
