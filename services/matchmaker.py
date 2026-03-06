import itertools
import logging
from dataclasses import dataclass

import aiosqlite

from database import feedback_repo
from services.feedback_service import get_pairwise_compatibility

log = logging.getLogger(__name__)

SKILL_WEIGHT = 0.6
SOCIAL_WEIGHT = 0.4
SKILL_RANGE_NORMALIZER = 400
NEW_PLAYER_DEFAULT_ADR = 150


@dataclass
class QueuedPlayer:
    discord_id: str
    pubg_name: str
    adr: float  # mode-specific, already resolved (with fallback/default)


def _skill_score(group: list[QueuedPlayer]) -> float:
    adrs = [p.adr for p in group]
    spread = max(adrs) - min(adrs)
    return max(0.0, 1.0 - spread / SKILL_RANGE_NORMALIZER)


async def _social_score(db: aiosqlite.Connection, group: list[QueuedPlayer]) -> float:
    if len(group) < 2:
        return 0.0
    scores = []
    for a, b in itertools.combinations(group, 2):
        scores.append(await get_pairwise_compatibility(db, a.discord_id, b.discord_id))
    return sum(scores) / len(scores)


async def _total_score(db: aiosqlite.Connection, group: list[QueuedPlayer]) -> float:
    skill = _skill_score(group)
    social = await _social_score(db, group)
    return SKILL_WEIGHT * skill + SOCIAL_WEIGHT * social


async def _has_block(db: aiosqlite.Connection, group: list[QueuedPlayer]) -> bool:
    for a, b in itertools.combinations(group, 2):
        if await feedback_repo.is_blocked(db, a.discord_id, b.discord_id):
            return True
    return False


async def _get_buddy_pairs(
    db: aiosqlite.Connection, players: list[QueuedPlayer]
) -> list[tuple[QueuedPlayer, QueuedPlayer]]:
    """Find confirmed buddy pairs within the player pool."""
    pairs = []
    ids = {p.discord_id: p for p in players}
    seen = set()
    for p in players:
        if p.discord_id in seen:
            continue
        buddies = await feedback_repo.get_confirmed_buddies(db, p.discord_id)
        for bid in buddies:
            if bid in ids and bid not in seen:
                pairs.append((p, ids[bid]))
                seen.add(p.discord_id)
                seen.add(bid)
                break
    return pairs


async def form_groups(
    db: aiosqlite.Connection,
    players: list[QueuedPlayer],
    group_size: int,
) -> list[list[QueuedPlayer]]:
    """Form optimal groups from the player pool.

    Returns a list of groups. Unmatched players remain ungrouped.
    """
    if len(players) < group_size:
        return []

    # Identify buddy pairs — they must be in the same group
    buddy_pairs = await _get_buddy_pairs(db, players)
    buddy_set = set()
    for a, b in buddy_pairs:
        buddy_set.add(a.discord_id)
        buddy_set.add(b.discord_id)

    # Build units: buddy pairs count as a single unit
    units: list[list[QueuedPlayer]] = []
    solo_players = []
    for p in players:
        if p.discord_id not in buddy_set:
            solo_players.append(p)

    for a, b in buddy_pairs:
        units.append([a, b])

    # Greedy group formation
    formed: list[list[QueuedPlayer]] = []
    remaining_solos = list(solo_players)
    remaining_units = list(units)

    while True:
        # Build candidate pool from remaining
        candidates: list[QueuedPlayer] = []
        for u in remaining_units:
            candidates.extend(u)
        candidates.extend(remaining_solos)

        if len(candidates) < group_size:
            break

        best_group: list[QueuedPlayer] | None = None
        best_score = float("-inf")

        # For small pools, try all combos; for large pools, use a simpler approach
        if len(candidates) <= 20:
            for combo in itertools.combinations(candidates, group_size):
                group = list(combo)

                # Check buddy constraint: if any buddy is in group, their partner must be too
                valid = True
                for a, b in buddy_pairs:
                    a_in = a in group
                    b_in = b in group
                    if a_in != b_in:
                        valid = False
                        break
                if not valid:
                    continue

                if await _has_block(db, group):
                    continue

                score = await _total_score(db, group)
                if score > best_score:
                    best_score = score
                    best_group = group
        else:
            # Tier-bucketed approach for larger pools
            candidates.sort(key=lambda p: p.adr)
            for i in range(0, len(candidates) - group_size + 1):
                group = candidates[i : i + group_size]

                valid = True
                for a, b in buddy_pairs:
                    a_in = a in group
                    b_in = b in group
                    if a_in != b_in:
                        valid = False
                        break
                if not valid:
                    continue

                if await _has_block(db, group):
                    continue

                score = await _total_score(db, group)
                if score > best_score:
                    best_score = score
                    best_group = group

        if best_group is None:
            break

        formed.append(best_group)

        # Remove matched players from pools
        matched_ids = {p.discord_id for p in best_group}
        remaining_solos = [p for p in remaining_solos if p.discord_id not in matched_ids]
        remaining_units = [u for u in remaining_units if u[0].discord_id not in matched_ids]

    return formed


async def form_squads(
    db: aiosqlite.Connection, players: list[QueuedPlayer]
) -> list[list[QueuedPlayer]]:
    return await form_groups(db, players, 4)


async def form_duos(
    db: aiosqlite.Connection, players: list[QueuedPlayer]
) -> list[list[QueuedPlayer]]:
    return await form_groups(db, players, 2)
