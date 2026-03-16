import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

import aiohttp

import config
from utils.rate_limiter import TokenBucket

log = logging.getLogger(__name__)

BASE_URL = f"https://api.pubg.com/shards/{config.PUBG_PLATFORM_SHARD}"
HEADERS = {
    "Authorization": f"Bearer {config.PUBG_API_KEY}",
    "Accept": "application/vnd.api+json",
}


@dataclass
class PlayerInfo:
    account_id: str
    name: str


@dataclass
class MatchParticipant:
    player_id: str
    damage_dealt: float
    kills: int
    assists: int
    win_place: int


@dataclass
class MatchData:
    match_id: str
    game_mode: str
    created_at: str  # ISO-8601
    participants: list[MatchParticipant]


class PUBGApiClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = TokenBucket(rate=10, period=60.0)
        self._player_id_cache: dict[str, str] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self, url: str, rate_limited: bool = True, priority: str = "high"
    ) -> dict | None:
        if rate_limited:
            await self._rate_limiter.acquire(priority=priority)

        session = await self._get_session()
        retries = 0
        while retries < 3:
            async with session.get(url) as resp:
                # Update rate limiter from headers
                remaining = resp.headers.get("X-RateLimit-Remaining")
                reset = resp.headers.get("X-RateLimit-Reset")
                if remaining is not None:
                    self._rate_limiter.update_from_headers(
                        int(remaining), float(reset) if reset else None
                    )

                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    wait = 2 ** retries
                    log.warning("Rate limited (429), retrying in %ds", wait)
                    retries += 1
                    await asyncio.sleep(wait)
                elif resp.status == 404:
                    return None
                else:
                    text = await resp.text()
                    log.error("PUBG API %s returned %d: %s", url, resp.status, text[:200])
                    return None
        log.error("PUBG API request failed after 3 retries: %s", url)
        return None

    async def get_player_by_name(self, name: str) -> PlayerInfo | None:
        # Check cache first
        if name.lower() in self._player_id_cache:
            cached_id = self._player_id_cache[name.lower()]
            return PlayerInfo(account_id=cached_id, name=name)

        url = f"{BASE_URL}/players?filter[playerNames]={name}"
        data = await self._request(url, rate_limited=True)
        if not data or not data.get("data"):
            return None

        player = data["data"][0]
        info = PlayerInfo(
            account_id=player["id"],
            name=player["attributes"]["name"],
        )
        self._player_id_cache[name.lower()] = info.account_id
        return info

    async def get_player_match_ids(
        self, player_id: str, priority: str = "high"
    ) -> list[str]:
        url = f"{BASE_URL}/players/{player_id}"
        data = await self._request(url, rate_limited=True, priority=priority)
        if not data or not data.get("data"):
            return []

        relationships = data["data"].get("relationships", {})
        matches = relationships.get("matches", {}).get("data", [])
        return [m["id"] for m in matches]

    async def get_match(self, match_id: str) -> MatchData | None:
        url = f"{BASE_URL}/matches/{match_id}"
        data = await self._request(url, rate_limited=False)  # NOT rate-limited
        if not data or not data.get("data"):
            return None

        attrs = data["data"]["attributes"]
        game_mode = attrs.get("gameMode", "")
        created_at = attrs.get("createdAt", "")

        participants = []
        for item in data.get("included", []):
            if item["type"] == "participant":
                stats = item["attributes"]["stats"]
                participants.append(
                    MatchParticipant(
                        player_id=stats.get("playerId", ""),
                        damage_dealt=stats.get("damageDealt", 0.0),
                        kills=stats.get("kills", 0),
                        assists=stats.get("assists", 0),
                        win_place=stats.get("winPlace", 0),
                    )
                )

        return MatchData(
            match_id=match_id,
            game_mode=game_mode,
            created_at=created_at,
            participants=participants,
        )

    async def get_current_season_id(self) -> str | None:
        url = f"{BASE_URL}/seasons"
        data = await self._request(url, rate_limited=True)
        if not data or not data.get("data"):
            return None

        for season in data["data"]:
            if season["attributes"].get("isCurrentSeason"):
                return season["id"]
        return None
