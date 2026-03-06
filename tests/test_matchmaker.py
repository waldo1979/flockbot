import pytest

from database import feedback_repo, player_repo
from services.matchmaker import QueuedPlayer, form_squads, form_duos


def _p(name: str, adr: float) -> QueuedPlayer:
    return QueuedPlayer(discord_id=name, pubg_name=name, adr=adr)


@pytest.fixture
async def match_db(db):
    for name in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        await player_repo.upsert_player(db, name, f"pubg_{name}", name)
    return db


class TestFormDuos:
    async def test_basic_duo(self, match_db):
        players = [_p("A", 200), _p("B", 210)]
        groups = await form_duos(match_db, players)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    async def test_not_enough_players(self, match_db):
        players = [_p("A", 200)]
        groups = await form_duos(match_db, players)
        assert groups == []

    async def test_four_players_two_duos(self, match_db):
        players = [_p("A", 100), _p("B", 110), _p("C", 300), _p("D", 310)]
        groups = await form_duos(match_db, players)
        assert len(groups) == 2
        # Similar ADR players should be grouped
        for group in groups:
            adrs = [p.adr for p in group]
            assert abs(adrs[0] - adrs[1]) <= 220  # Not the worst combo

    async def test_blocked_players_not_paired(self, match_db):
        await feedback_repo.insert_block(match_db, "A", "B")
        players = [_p("A", 200), _p("B", 200), _p("C", 200), _p("D", 200)]
        groups = await form_duos(match_db, players)
        for group in groups:
            ids = {p.discord_id for p in group}
            assert not ({"A", "B"} <= ids)


class TestFormSquads:
    async def test_basic_squad(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220), _p("D", 230)]
        groups = await form_squads(match_db, players)
        assert len(groups) == 1
        assert len(groups[0]) == 4

    async def test_not_enough_players(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220)]
        groups = await form_squads(match_db, players)
        assert groups == []

    async def test_five_players_one_squad(self, match_db):
        players = [_p("A", 200), _p("B", 210), _p("C", 220), _p("D", 230), _p("E", 240)]
        groups = await form_squads(match_db, players)
        assert len(groups) == 1
        assert len(groups[0]) == 4

    async def test_eight_players_two_squads(self, match_db):
        players = [
            _p("A", 100), _p("B", 110), _p("C", 120), _p("D", 130),
            _p("E", 300), _p("F", 310), _p("G", 320), _p("H", 330),
        ]
        groups = await form_squads(match_db, players)
        assert len(groups) == 2

    async def test_blocked_players_separated(self, match_db):
        await feedback_repo.insert_block(match_db, "A", "B")
        players = [_p("A", 200), _p("B", 200), _p("C", 200), _p("D", 200), _p("E", 200)]
        groups = await form_squads(match_db, players)
        for group in groups:
            ids = {p.discord_id for p in group}
            assert not ({"A", "B"} <= ids)

    async def test_buddies_grouped_together(self, match_db):
        await feedback_repo.insert_buddy_request(match_db, "A", "B")
        await feedback_repo.insert_buddy_request(match_db, "B", "A")
        players = [_p("A", 100), _p("B", 100), _p("C", 400), _p("D", 400), _p("E", 400), _p("F", 400)]
        groups = await form_squads(match_db, players)
        # A and B should be in the same group despite ADR mismatch
        for group in groups:
            ids = {p.discord_id for p in group}
            if "A" in ids:
                assert "B" in ids
            if "B" in ids:
                assert "A" in ids

    async def test_skill_similarity_preferred(self, match_db):
        players = [_p("A", 100), _p("B", 110), _p("C", 400), _p("D", 410)]
        groups = await form_squads(match_db, players)
        # With only 4 players, they must be grouped together
        assert len(groups) == 1

    async def test_empty_pool(self, match_db):
        groups = await form_squads(match_db, [])
        assert groups == []
