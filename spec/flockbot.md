# Flockbot Specification

> **Version**: 0.1.0
> **Status**: Draft
> **Last Updated**: 2026-03-04

Flockbot is a Discord bot that forms PUBG squads and duos by matching players on skill level (ADR) and social compatibility (peer feedback). Players queue by joining voice channel lobbies; the bot matches groups and moves them into temporary voice channels.

---

## 1. System Overview

### 1.1 Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Discord framework | discord.py 2.4+ (slash commands via `app_commands`) |
| Database | SQLite via aiosqlite (WAL mode) |
| HTTP client | aiohttp (PUBG API) |
| Dependency management | uv (`pyproject.toml` + `uv.lock`) |
| Deployment | Docker (multi-stage build) + docker-compose |

### 1.2 External Dependencies

| Service | Purpose | Auth |
|---|---|---|
| Discord API | Bot gateway + interactions | Bot token (env: `DISCORD_TOKEN`) |
| PUBG API (`api.pubg.com`) | Player stats, match data | Bearer token (env: `PUBG_API_KEY`) |

### 1.3 Supported Game Modes

Only **FPP** (first-person perspective) modes are supported:

- `squad-fpp`
- `duo-fpp`

All TPP data is ignored. No other modes are tracked.

### 1.4 Platform

PC (Steam) only. PUBG API shard: `steam`.

---

## 2. Player Registration

### 2.1 Registration Flow

1. Player invokes `/register <pubg_name>` in any text channel.
2. Bot calls PUBG API `GET /shards/steam/players?filter[playerNames]=<pubg_name>`.
3. If found: bot checks whether the returned `pubg_id` is already linked to a **different** Discord user. If so, registration is rejected with: *"**{pubg_name}** is already registered to another player. Contact an admin if this is your account."* (Re-registering the same account from the same Discord user is allowed, e.g., after a PUBG name change.)
4. Bot creates or updates a `players` row linking `discord_id` to `pubg_id` and `pubg_name`.
5. Bot sets the player's **Discord server nickname** to `pubg_name` via `member.edit(nick=pubg_name)`.
6. Bot triggers an initial stats refresh (Phase 2.2).
7. Bot responds ephemerally with confirmation and initial stats.

### 2.2 Name Enforcement

- The Discord server nickname **must** match the PUBG player name.
- This is enforced automatically at registration time.
- If the bot lacks permission to rename (e.g., server owner), it warns the player to set their nickname manually.

---

## 3. PUBG Stats

### 3.1 Data Ingestion

The PUBG API only exposes match history for the last **14 days**. To build a complete season record, the bot continuously ingests match data:

- **Background task**: Every **2 hours**, iterate through all registered players and fetch their recent matches.
- Stagger requests at 1 player per rate-limit cycle to stay within the 10 req/min limit.
- For each player:
  1. `GET /shards/steam/players/{id}` — returns up to ~20 recent match IDs. **(rate-limited: 1 call)**
  2. For each match ID not already in the database: `GET /shards/steam/matches/{matchId}` — **(NOT rate-limited)**.
  3. From the match response, find the participant entry matching the player's `pubg_id`.
  4. If `gameMode` is `squad-fpp` or `duo-fpp`: extract `damageDealt`, `kills`, `assists`, `winPlace`, `createdAt`, and the match's season. Store in `match_stats`.
  5. Discard all non-FPP matches.
- On-demand refresh via `/stats refresh` (5-minute cooldown per player).

### 3.2 Season Tracking

- The bot fetches the current season ID from `GET /shards/steam/seasons` once per day and caches it in memory.
- Each `match_stats` row is tagged with its `season`.
- When a new season is detected, cached ADR values naturally reset (no current-season matches yet exist).

### 3.3 ADR Calculation

ADR (Average Damage per Round) is calculated **per mode** and **per season**:

```
ADR(mode, season) = SUM(damage_dealt) / COUNT(*)
                    WHERE game_mode = mode AND season = season
```

### 3.4 ADR Fallback Chain

For a given mode (e.g., `squad-fpp`):

1. **Current season**: If the player has **≥10 matches** in the current season for this mode, use that ADR.
2. **Previous season**: If <10 current-season matches, fall back to the previous season's ADR for the same mode.
3. **"New"**: If neither season has ≥10 matches, the player is labeled **"New"**.

The term "unranked" is never used (it is a PUBG-specific concept).

### 3.5 ADR Tiers

Tiers are numeric threshold labels, not metals:

| ADR Range | Tier Label |
|---|---|
| 0–99 | `<100` |
| 100–199 | `100+` |
| 200–249 | `200+` |
| 250–299 | `250+` |
| 300–399 | `300+` |
| 400+ | `400+` |

Players labeled "New" have no tier.

### 3.6 Mode-Specific ADR

A player has **two independent ADR values**:

- **Squad-FPP ADR**: used when the player is in the squad queue.
- **Duo-FPP ADR**: used when the player is in the duo queue.

Both are cached on the `players` row and updated on each stats refresh.

### 3.7 PUBG API Rate Limiting

- **Rate-limited endpoints** (10 req/min): `/players`, `/seasons`
- **Exempt endpoints** (unlimited): `/matches/{id}`, telemetry URLs
- Implementation: async token-bucket (10 tokens, refills 10 per 60 seconds)
- On HTTP 429: exponential backoff with jitter (1s, 2s, 4s; max 3 retries)
- Response headers `X-RateLimit-Remaining` and `X-RateLimit-Reset` are parsed to adjust bucket state.
- Player ID lookups are cached in-memory (LRU, 128 entries, 24h TTL) since player IDs never change.

---

## 4. Social Feedback System

### 4.1 Design Principles

- Rooted in sociometric research and Dunbar's number (~60–90 meaningful gaming relationships).
- Binary active feedback (thumbs up/down) with exponential decay minimizes cognitive overhead.
- Passive signals (co-play tracking) supplement active feedback with zero player effort.
- "Never Again" and "Best Buddy" are strong social signals stored permanently.

### 4.2 Feedback Entry Points

Two ways to give feedback:

1. **Slash command**: `/feedback <@player>` → bot responds with an ephemeral message containing 4 buttons.
2. **Context menu**: Right-click any user → Apps → **"Rate Teammate"** → same ephemeral button prompt.

### 4.3 Feedback Buttons

| Button | Style | Value | Behavior |
|---|---|---|---|
| Thumbs Up | Green | `+1` in `feedback` table | Records positive feedback |
| Thumbs Down | Red | `-1` in `feedback` table | Records negative feedback |
| Never Again | Danger/Black | Row in `blocks` table | Confirmation prompt first, then permanent block |
| Best Buddy | Blurple | Row in `buddies` table | If mutual, confirms the bond |

All responses are **ephemeral** (only the invoking player sees them).

### 4.4 Feedback Constraints

- A player may only give feedback to the same person **once per 24 hours**.
- A player cannot give feedback to themselves (enforced by DB constraint).
- Feedback values are anonymous in display — a player can see their aggregate reputation but not individual voters.

### 4.5 Exponential Decay

Feedback entries lose weight over time:

| Age | Weight |
|---|---|
| 0–2 weeks | 1.00 |
| 2–4 weeks | 0.75 |
| 4–6 weeks | 0.50 |
| 6–8 weeks | 0.25 |
| >8 weeks | 0.00 |

### 4.6 Feedback Cleanup

- A background task runs **daily** and deletes feedback rows older than **84 days** (12 weeks).
- Blocks and buddy bonds are **never** cleaned up.

### 4.7 "Never Again" Blocks

- A hard block that prevents two players from **ever** being placed in the same group.
- Stored permanently in the `blocks` table (no decay).
- Either direction blocks the pairing: if A blocks B, they cannot be grouped regardless of who initiated.
- A player can remove their own block via `/unblock <@player>`.
- Before recording, the bot shows a confirmation prompt: *"Are you sure? This blocks them from your groups permanently."*

### 4.8 "Best Buddy" Bonds

- A strong positive signal indicating a player wants to **always** play with another.
- **Must be mutual**: if only A marks B as best buddy, it is treated as a regular thumbs-up. The bond only activates when both A→B and B→A exist.
- When mutual, the `confirmed` field on both rows is set to `1`.
- Effects of a confirmed buddy bond:
  - The matchmaker **always groups buddies together** (treats them as a single unit).
  - If one buddy is in the LFG lobby and the other is online but not in the lobby, the bot **notifies the absent buddy** and **holds a slot for up to 5 minutes**.
- A player can view their confirmed buddy pairs via `/buddies`.

### 4.9 Passive Co-Play Tracking

- The bot monitors `on_voice_state_update` events.
- When two or more registered players share a voice channel for **≥15 minutes**, the bot logs the pair to `co_play_log` (one entry per pair per day, with a count field that increments).
- The canonical ordering constraint `player_a < player_b` prevents duplicate pair entries.
- Co-play data is used as a weak positive signal in compatibility scoring (see §5.3).

### 4.10 Pairwise Compatibility Score

```
direct_score = avg(decay_weighted feedback between A and B, both directions)
               Range: -1.0 to +1.0. Default 0.0 if no feedback exists.

co_play_signal = min(co_play_count_last_8_weeks / 10, 1.0)
                 Range: 0.0 to 1.0. 10+ sessions = max signal.

If direct_score < 0:
    compatibility = direct_score          # Negative feedback dominates
Else:
    compatibility = 0.7 * direct_score + 0.3 * co_play_signal
```

---

## 5. LFG and Matchmaking

### 5.1 Voice Channel Setup

The Discord server must have two voice channels (detected by name):

- **"LFG Squad"** — players join here to queue for squad (4-player) groups.
- **"LFG Duo"** — players join here to queue for duo (2-player) groups.

A channel category **"PUBG VOICE"** is used as the parent for bot-created temporary channels.

### 5.2 LFG Flow

1. A registered player joins the "LFG Squad" or "LFG Duo" voice channel.
2. The bot detects this via `on_voice_state_update` and adds the player to the in-memory matching pool.
3. If the player has a confirmed buddy who is **online but not in the lobby**, the bot sends a notification: *"@BuddyB, your buddy @BuddyA is looking for a squad! Join LFG Squad to play together."* The bot holds a slot for the buddy for **up to 5 minutes**.
4. When the pool has enough players (4 for squad, 2 for duo), the matchmaker runs.
5. The matchmaker forms optimal groups (see §5.3) and for each group:
   a. Creates a **temporary voice channel** (e.g., "Squad #1") under the PUBG VOICE category with **per-user permission overrides**: `@everyone` is denied Connect, each matched player is granted Connect, and the bot retains Connect/Move Members/Manage Channels. This ensures only matched players can join the channel, and they can **reconnect if they disconnect**.
   b. **Moves** all matched players into the temporary channel.
   c. Posts a match announcement in a text channel showing the group members and their tiers.
6. When a temporary voice channel becomes **empty**, the bot deletes it.
7. If a player **leaves** the LFG lobby before being matched, they are removed from the pool.

### 5.3 Matching Algorithm

**Scoring function** for a candidate group G of size N:

```
skill_score(G)  = 1.0 - (max_adr(G) - min_adr(G)) / 400
social_score(G) = mean(pairwise_compatibility(a, b) for all pairs in G)

r = relaxation_factor(G)   # see §5.6
effective_skill_weight = 0.6 * (1.0 - r)
baseline = 0.6 * r

total_score(G)  = effective_skill_weight * skill_score + 0.4 * social_score + baseline
```

At r=0 (fresh queue): `0.6*skill + 0.4*social` (unchanged).
At r=1 (5+ min wait): `0.4*social + 0.6` (skill irrelevant, social still matters).

- ADR used is **mode-specific**: squad-fpp ADR for squad queue, duo-fpp ADR for duo queue.
- Players labeled "New" are assigned a default ADR of 150 for matching purposes.

**Hard constraints** (violating groups are never formed):

- No group may contain two players with a "Never Again" block between them (in either direction).
- Confirmed buddy pairs must be placed in the same group (treated as a single unit during combination generation).

**Algorithm**:

- For pools of **≤20 players**: evaluate all `itertools.combinations` of the appropriate group size, score each, and greedily select the highest-scoring group, remove those players, repeat.
- For pools of **>20 players**: bucket players by ADR tier first, form groups within tiers, then attempt cross-tier matching for remainders.

### 5.4 Queue State

Queue state is **in-memory only** — derived from who is currently in the LFG voice channels. There is no persistent queue table.

Pool state is stored on the bot instance (`bot.lfg_pools`) as `dict[int, dict[int, datetime]]` — mapping channel ID → {discord user ID → join time}. This ensures a single source of truth shared across all cogs (discord.py's `load_extension` creates separate module instances from regular imports, so module-level state would be split).

On startup (`on_ready`), the bot scans both LFG voice channels and rebuilds the in-memory pools from any registered players already present. This ensures queue state survives container restarts and upgrades without requiring players to leave and rejoin.

### 5.5 Queue Status Display

The `/queue` command shows an ephemeral status for the invoking player. If the player is not queued, it says so. If queued, it shows a single line with their queue info:

```
LFG Squad — Waiting 1m 15s · need 2 more · laxative in 0m 45s
LFG Duo — Waiting 3m 30s · fully open in 1m 30s
LFG Squad — Waiting 6m 10s · need 1 more · wide open
```

Fields (separated by ` · `):
- **Wait time** — how long the player has been queued.
- **Need X more** — how many additional players are needed to fill a group (omitted when the pool is full).
- **Laxative countdown** — time until the next relaxation phase:
  - `laxative in Xm Ys` — skill matching is still strict, shows countdown to relaxation start (2 min effective wait).
  - `fully open in Xm Ys` — relaxation is active, shows countdown to full relaxation (5 min effective wait).
  - `wide open` — skill matching is fully relaxed.
- Countdowns account for the player's queue preference (FAST halves the real time to each phase).
- The response is **ephemeral** to avoid channel spam.

### 5.6 Skill Relaxation

Skill matching loosens over time so that no player waits more than 5 minutes for a group.

**Relaxation curve** — based on the longest effective wait in a candidate group:

| Effective wait | Relaxation factor (r) | Effect |
|---|---|---|
| 0–2 min | 0.0 | Strict: full skill weight (0.6) |
| 2–5 min | Linear 0.0→1.0 | Skill weight decreases linearly |
| ≥5 min | 1.0 | Open: skill ignored, social + baseline only |

**Queue preference** — players choose their matching speed via `/queuepref`:

| Preference | Effect on effective wait |
|---|---|
| `skill` (default) | Raw wait time used |
| `fast` | Effective wait = raw wait × 2 (relaxation happens twice as fast) |

Stored in `players.queue_preference` (persisted in SQLite).

**Hard constraints are never relaxed**: blocks and buddy bonds are enforced regardless of relaxation factor.

**Periodic re-evaluation**: a `@tasks.loop(seconds=30)` background task in `lfg_handler.py` re-runs the matchmaker on all LFG pools, so long-waiting players benefit from relaxation even when no new player joins.

**Constants** (`services/matchmaker.py`):

| Constant | Value | Description |
|---|---|---|
| `RELAXATION_START_SECS` | 120 | Seconds before relaxation begins |
| `RELAXATION_FULL_SECS` | 300 | Seconds at which skill is fully relaxed |

---

## 6. Slash Commands

### 6.1 Registration and Stats

| Command | Description | Response | Cooldown |
|---|---|---|---|
| `/register <pubg_name>` | Link Discord account to PUBG name, set server nickname | Ephemeral: confirmation + initial stats | 60s |
| `/stats` | Show your own stats (squad-fpp ADR, duo-fpp ADR, tiers, match counts, season) | Public embed | 30s |
| `/stats lookup <@player>` | Show another registered player's stats | Public embed | 15s |
| `/stats refresh` | Force-refresh stats from PUBG API | Ephemeral: updated stats | 300s |
| `/leaderboard` | Server ADR leaderboard (top 10, selectable by mode) | Public embed | 60s |

### 6.2 Social Feedback

| Command | Description | Response | Cooldown |
|---|---|---|---|
| `/feedback <@player>` | Rate a player (shows 4 buttons) | Ephemeral: FeedbackView | 10s |
| `/unblock <@player>` | Remove a "Never Again" block you placed | Ephemeral: confirmation | 30s |
| `/buddies` | List your confirmed buddy pairs | Ephemeral: buddy list | 30s |
| *Context menu*: "Rate Teammate" | Right-click user → Apps → Rate Teammate | Ephemeral: FeedbackView | — |

### 6.3 Queue

| Command | Description | Response | Cooldown |
|---|---|---|---|
| `/queue` | Show your queue status: wait time, players needed, laxative countdown | Ephemeral | 10s |
| `/queuepref <skill\|fast>` | Set matching preference: skill (tight matches) or fast (quicker groups) | Ephemeral | 10s |
| `/kick <@player>` | (Admin) Remove a player from LFG lobby | Ephemeral: confirmation | — |

### 6.4 Admin

| Command | Description | Response | Cooldown |
|---|---|---|---|
| `/admin sync` | Sync slash commands to Discord | Ephemeral: confirmation | — |
| `/admin cleanup` | Manually run stale data cleanup | Ephemeral: summary of deleted rows | — |
| `/admin transfer <pubg_name> <@to>` | Transfer a PUBG account linkage to a different Discord user (dispute resolution) | Ephemeral: confirmation | — |

### 6.5 Command Throttling

All player-facing commands enforce per-user cooldowns to prevent channel spam and protect backend resources. Cooldowns are tracked in-memory per Discord user ID. If a player invokes a command before their cooldown expires, they receive an ephemeral message with the remaining wait time.

Admin commands (`/admin sync`, `/admin cleanup`, `/queue kick`) are exempt from cooldowns.

Design rationale for a ~200-player server:
- **High-frequency commands** (`/queue status`, `/feedback`): 10s — players may check these several times per session.
- **Medium-frequency commands** (`/stats`, `/lookup`, `/buddies`, `/unblock`): 15–30s — data changes infrequently within a session.
- **Low-frequency commands** (`/register`, `/leaderboard`): 60s — one-time or community-wide data.
- **API-bound commands** (`/refresh`): 300s — protects the PUBG API rate limit budget.

Implementation: a shared `@cooldown(seconds)` decorator in `utils/cooldown.py` applied to each command handler.

---

## 7. Database Schema

All timestamps are ISO-8601 strings. SQLite `datetime('now')` for defaults.

### 7.1 `schema_version`

Tracks applied schema migrations.

| Column | Type | Constraints |
|---|---|---|
| `version` | INTEGER | PRIMARY KEY |
| `applied_at` | TEXT | NOT NULL, DEFAULT datetime('now') |

### 7.2 `players`

Discord-to-PUBG account linkage and cached stats.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `discord_id` | TEXT | PRIMARY KEY | Discord user snowflake |
| `pubg_id` | TEXT | UNIQUE | PUBG account ID |
| `pubg_name` | TEXT | NOT NULL | PUBG in-game name |
| `registered_at` | TEXT | NOT NULL, DEFAULT now | |
| `last_stats_update` | TEXT | | Last refresh timestamp |
| `squad_fpp_adr` | REAL | | Cached squad-fpp ADR |
| `squad_fpp_tier` | TEXT | | Tier label for squad-fpp |
| `squad_fpp_matches` | INTEGER | | Match count (current season) |
| `duo_fpp_adr` | REAL | | Cached duo-fpp ADR |
| `duo_fpp_tier` | TEXT | | Tier label for duo-fpp |
| `duo_fpp_matches` | INTEGER | | Match count (current season) |
| `adr_season` | TEXT | | Season ID these cached values are from |
| `queue_preference` | TEXT | DEFAULT 'skill' | Matching preference: 'skill' or 'fast' |

### 7.3 `match_stats`

Per-match damage data fetched from PUBG API. Only FPP modes stored.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `discord_id` | TEXT | NOT NULL, FK → players |
| `match_id` | TEXT | NOT NULL |
| `game_mode` | TEXT | NOT NULL, CHECK IN ('squad-fpp', 'duo-fpp') |
| `season` | TEXT | NOT NULL |
| `damage_dealt` | REAL | NOT NULL |
| `kills` | INTEGER | NOT NULL |
| `assists` | INTEGER | NOT NULL |
| `win_place` | INTEGER | NOT NULL |
| `match_date` | TEXT | NOT NULL |
| `fetched_at` | TEXT | NOT NULL, DEFAULT now |
| | | UNIQUE(discord_id, match_id) |

### 7.4 `feedback`

Binary thumbs up/down entries. Subject to exponential decay and 12-week cleanup.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `from_user` | TEXT | NOT NULL, FK → players |
| `to_user` | TEXT | NOT NULL, FK → players |
| `value` | INTEGER | NOT NULL, CHECK IN (-1, 1) |
| `created_at` | TEXT | NOT NULL, DEFAULT now |
| | | CHECK(from_user != to_user) |

### 7.5 `blocks`

Permanent "Never Again" blocks. No decay.

| Column | Type | Constraints |
|---|---|---|
| `from_user` | TEXT | NOT NULL, FK → players |
| `to_user` | TEXT | NOT NULL, FK → players |
| `created_at` | TEXT | NOT NULL, DEFAULT now |
| | | PRIMARY KEY (from_user, to_user) |
| | | CHECK(from_user != to_user) |

### 7.6 `buddies`

Best buddy bonds. Requires mutual confirmation.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `from_user` | TEXT | NOT NULL, FK → players | |
| `to_user` | TEXT | NOT NULL, FK → players | |
| `confirmed` | INTEGER | NOT NULL, DEFAULT 0 | 1 when mutual |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| | | PRIMARY KEY (from_user, to_user) | |
| | | CHECK(from_user != to_user) | |

### 7.7 `co_play_log`

Passive tracking of who plays together. One row per player-pair per day.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `player_a` | TEXT | NOT NULL | Lexicographically smaller discord_id |
| `player_b` | TEXT | NOT NULL | Lexicographically larger discord_id |
| `date` | TEXT | NOT NULL | YYYY-MM-DD |
| `count` | INTEGER | NOT NULL, DEFAULT 1 | Incremented per co-play session |
| | | UNIQUE(player_a, player_b, date) | |
| | | CHECK(player_a < player_b) | Canonical ordering |

---

## 8. Background Tasks

| Task | Frequency | Description |
|---|---|---|
| Welcome messages | On startup | Purge bot messages in #rules, re-post from `docs/discord-welcome.md` (3 messages) |
| Stats refresh | Every 2 hours | Fetch recent matches for all registered players, store FPP matches, recalculate per-mode ADR |
| Season check | Daily | Fetch current season ID from PUBG API, detect season transitions |
| Feedback cleanup | Daily | Delete feedback rows older than 84 days (12 weeks) |
| Periodic match | Every 30 seconds | Re-run matchmaker on LFG pools so long-waiting players benefit from skill relaxation |

---

## 9. Discord Server Requirements

### 9.1 Bot Permissions

| Permission | Reason |
|---|---|
| Manage Channels | Create/delete temporary voice channels |
| Manage Nicknames | Set player nicknames on registration |
| Manage Roles | Set permissions on temporary channels |
| View Channels | Read server channel structure |
| Connect | Join voice channels |
| Move Members | Move matched players to temp channels |
| Send Messages | Post match announcements, buddy notifications |
| Embed Links | Rich embed responses |

### 9.2 Gateway Intents

| Intent | Privileged? | Reason |
|---|---|---|
| `GUILD_VOICE_STATES` | No | Detect voice channel joins/leaves for LFG and co-play tracking |

### 9.3 Required Channel Structure

```
📋 INFO
  #rules
  #announcements

💬 GENERAL
  #general
  #bot-commands

🎮 LFG
  🔊 LFG Squad
  🔊 LFG Duo

🔊 PUBG VOICE
  (bot creates temporary channels here)
```

### 9.4 Scaling Notes

- **Community Server** mode is not required.
- No privileged intents are needed — bot verification is not required until 100+ servers (this is a single-server bot).
- Discord limits: 500 channels per server. Temporary channels auto-delete when empty, so this is not a practical concern.
- Server boosts are optional (Level 3 provides 384kbps audio vs 96kbps default).

---

## 10. Configuration

### 10.1 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Bot token from Discord Developer Portal |
| `PUBG_API_KEY` | Yes | API key from developer.pubg.com |
| `DATABASE_PATH` | No | Path to SQLite file (default: `data/flockbot.db`) |
| `GUILD_ID` | No | Dev guild ID for instant slash command sync |

### 10.2 Tunable Constants

| Constant | Default | Location | Description |
|---|---|---|---|
| `SKILL_WEIGHT` | 0.6 | `services/matchmaker.py` | Weight of skill similarity in matching |
| `SOCIAL_WEIGHT` | 0.4 | `services/matchmaker.py` | Weight of social compatibility in matching |
| `BUDDY_WAIT_MINUTES` | 5 | `events/lfg_handler.py` | How long to hold a slot for an absent buddy |
| `STATS_REFRESH_HOURS` | 2 | `events/on_ready.py` | Interval between background stats refreshes |
| `MIN_MATCHES_FOR_ADR` | 10 | `services/stats_service.py` | Minimum matches before showing ADR (else fallback) |
| `NEW_PLAYER_DEFAULT_ADR` | 150 | `services/matchmaker.py` | ADR assumed for "New" players in matching |
| `FEEDBACK_MAX_AGE_DAYS` | 84 | `services/feedback_service.py` | When raw feedback is deleted |
| `CO_PLAY_NORMALIZER` | 10 | `services/feedback_service.py` | Co-play sessions for max signal |
| `RELAXATION_START_SECS` | 120 | `services/matchmaker.py` | Seconds before skill relaxation begins |
| `RELAXATION_FULL_SECS` | 300 | `services/matchmaker.py` | Seconds at which skill weight reaches zero |

---

## 11. Project Structure

```
flockbot/
  bot.py                          # Entry point: FlockBot subclass
  config.py                       # .env loader, typed constants
  pyproject.toml                  # uv project metadata + dependencies
  .python-version                 # 3.11
  Dockerfile                      # Multi-stage: uv install → slim runtime
  docker-compose.yml              # Single service, data volume, env_file
  .env.example
  .gitignore
  .dockerignore
  CLAUDE.md
  spec/
    flockbot.md                   # This file (source of truth)
  commands/
    __init__.py
    admin.py                      # /admin sync, /admin cleanup
    stats.py                      # /register, /stats, /leaderboard
    feedback.py                   # /feedback, /unblock, /buddies, context menu
    queue.py                      # /queue status, /queue kick
  events/
    __init__.py
    on_ready.py                   # Startup, background task scheduling
    lfg_handler.py                # Voice-based LFG detection, temp channel mgmt
    voice_tracker.py              # Passive co-play logging
  services/
    __init__.py
    pubg_api.py                   # PUBG API client, rate limiting, caching
    stats_service.py              # ADR calculation, tier assignment, season fallback
    feedback_service.py           # Decay scoring, blocks, buddies, compatibility
    matchmaker.py                 # Squad/duo formation algorithm
  database/
    __init__.py
    connection.py                 # aiosqlite lifecycle (init, WAL, shutdown)
    schema.sql                    # DDL for all tables
    migrations.py                 # Schema version tracking
    player_repo.py                # Player CRUD
    match_repo.py                 # Match stats CRUD
    feedback_repo.py              # Feedback, blocks, buddies CRUD
  utils/
    __init__.py
    embeds.py                     # Discord embed builders
    rate_limiter.py               # Async token-bucket
    time_helpers.py               # Decay weight function
    views.py                      # FeedbackView, confirmation prompts
  tests/
    __init__.py
    conftest.py                   # In-memory SQLite fixtures, mock PUBG API
    test_stats_service.py         # ADR calc, tiers, season fallback, mode filtering
    test_feedback_service.py      # Decay, blocks, buddy confirmation
    test_matchmaker.py            # Grouping, veto, buddy bonding, edge cases
    test_pubg_api.py              # Mock HTTP, rate limiter, 429 retry
    test_rate_limiter.py          # Token bucket behavior
    test_decay.py                 # Parametrized decay weight boundaries
```
