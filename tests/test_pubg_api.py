import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.pubg_api import PUBGApiClient, PlayerInfo, MatchData


def _mock_response(status=200, json_data=None, headers=None):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value="error")
    resp.headers = headers or {}
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestGetPlayerByName:
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_returns_player_info(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(
            status=200,
            json_data={
                "data": [{
                    "type": "player",
                    "id": "account.abc123",
                    "attributes": {"name": "TestPlayer"},
                }]
            },
        ))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        result = await client.get_player_by_name("TestPlayer")
        assert result is not None
        assert result.account_id == "account.abc123"
        assert result.name == "TestPlayer"
        await client.close()

    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_returns_none_for_404(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(status=404))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        result = await client.get_player_by_name("NonExistent")
        assert result is None
        await client.close()

    async def test_uses_cache_on_second_call(self):
        client = PUBGApiClient()
        client._player_id_cache["testplayer"] = "account.cached"
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        result = await client.get_player_by_name("TestPlayer")
        assert result is not None
        assert result.account_id == "account.cached"
        await client.close()


class TestGetMatch:
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_returns_match_data(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(
            status=200,
            json_data={
                "data": {
                    "type": "match",
                    "id": "match-001",
                    "attributes": {
                        "gameMode": "squad-fpp",
                        "createdAt": "2026-03-01T12:00:00Z",
                    },
                },
                "included": [
                    {
                        "type": "participant",
                        "attributes": {
                            "stats": {
                                "playerId": "account.abc123",
                                "damageDealt": 312.5,
                                "kills": 3,
                                "assists": 1,
                                "winPlace": 2,
                            }
                        },
                    }
                ],
            },
        ))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        result = await client.get_match("match-001")
        assert result is not None
        assert result.match_id == "match-001"
        assert result.game_mode == "squad-fpp"
        assert len(result.participants) == 1
        assert result.participants[0].damage_dealt == 312.5
        assert result.participants[0].kills == 3
        await client.close()

    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_match_not_rate_limited(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(
            status=200,
            json_data={
                "data": {"type": "match", "id": "m1", "attributes": {"gameMode": "squad-fpp", "createdAt": ""}},
                "included": [],
            },
        ))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        await client.get_match("m1")
        # Match endpoint should NOT call rate limiter
        client._rate_limiter.acquire.assert_not_called()
        await client.close()


class TestRetryOn429:
    @patch("services.pubg_api.asyncio.sleep", new_callable=AsyncMock)
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_retries_on_429_then_succeeds(self, mock_session_cls, mock_sleep):
        responses = [
            _mock_response(status=429, headers={}),
            _mock_response(status=200, json_data={
                "data": [{"id": "account.abc", "attributes": {"name": "Retry"}}]
            }),
        ]
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            resp = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(side_effect=side_effect)
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()
        client._rate_limiter.update_from_headers = MagicMock()

        result = await client.get_player_by_name("Retry")
        assert result is not None
        assert result.account_id == "account.abc"
        # Should have slept once (exponential backoff: 2^0 = 1s)
        mock_sleep.assert_awaited_once_with(1)
        await client.close()

    @patch("services.pubg_api.asyncio.sleep", new_callable=AsyncMock)
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_gives_up_after_3_retries(self, mock_session_cls, mock_sleep):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(status=429))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()
        client._rate_limiter.update_from_headers = MagicMock()

        result = await client.get_player_by_name("NeverWorks")
        assert result is None
        assert mock_sleep.await_count == 3
        await client.close()


class TestGetCurrentSeason:
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_finds_current_season(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(
            status=200,
            json_data={
                "data": [
                    {"id": "division.bro.official.pc-2018-01", "attributes": {"isCurrentSeason": False}},
                    {"id": "division.bro.official.pc-2018-02", "attributes": {"isCurrentSeason": True}},
                ]
            },
        ))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = AsyncMock()
        client._rate_limiter.acquire = AsyncMock()

        result = await client.get_current_season_id()
        assert result == "division.bro.official.pc-2018-02"
        await client.close()


class TestRateLimitHeaders:
    @patch("services.pubg_api.aiohttp.ClientSession")
    async def test_updates_bucket_from_headers(self, mock_session_cls):
        session = AsyncMock()
        session.closed = False
        session.get = MagicMock(return_value=_mock_response(
            status=200,
            json_data={"data": [{"id": "account.x", "attributes": {"name": "H"}}]},
            headers={"X-RateLimit-Remaining": "7", "X-RateLimit-Reset": "1709640000"},
        ))
        mock_session_cls.return_value = session

        client = PUBGApiClient()
        client._session = session
        client._rate_limiter = MagicMock()
        client._rate_limiter.acquire = AsyncMock()

        await client.get_player_by_name("H")
        client._rate_limiter.update_from_headers.assert_called_once_with(7, 1709640000.0)
        await client.close()
