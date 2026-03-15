# Welcome to Flockbot

Post each section below as a separate message in your Discord #rules channel.

---

**MESSAGE 1:**

## Welcome

Flockbot matches you into PUBG squads and duos based on skill and social compatibility. No more awkward random fills — join the lobby, get matched, play.

## Getting Started

**Step 1: Register your PUBG name**
Type `/register YourPUBGName` in any text channel. This links your Discord account to your PUBG stats. Your server nickname will be set to your PUBG name. Each PUBG account can only be linked to one Discord user — contact an admin if you need to transfer an account.

**Step 2: Check your stats**
Type `/stats` to see your ADR (Average Damage per Round) for squad and duo FPP. Your ADR determines your skill tier.

**Step 3: Queue up**
Join one of the voice lobbies to find a group:
- **LFG Squad** — queues you for a 4-player squad
- **LFG Duo** — queues you for a 2-player duo

When enough players are in the lobby, Flockbot forms a group and moves you into a temporary voice channel (with a random name like "Sneaky Corgi"). If you disconnect, just rejoin the same channel — it stays open for 10 minutes. When everyone leaves for good, the channel is cleaned up automatically.

**How matching works over time:**
The bot starts with tight skill matching. If you're waiting a while, the laxative kicks in — it gradually loosens the skill requirement so you get a game faster. Type `/queue` to see your wait time, how many more players are needed, and when the laxative kicks in. Social compatibility (feedback, buddies) always matters — blocks are never overridden.

**Want faster matches?** Type `/queuepref fast` — the laxative kicks in sooner. Use `/queuepref skill` to go back to tighter matches.

---

**MESSAGE 2:**

## Skill Tiers

Your tier is based on your FPP ADR for the current season:

- **<100** — Getting started
- **100+** — Finding your feet
- **200+** — Solid player
- **250+** — Above average
- **300+** — Strong performer
- **400+** — Top tier

Players with fewer than 10 matches this season show as **New**.

## Social Connections

The more time you spend with someone in voice channels, the more likely the matchmaker pairs you together. No buttons to click — just hang out.

For strong feelings, use `/feedback @player` or right-click a player → **Apps → Rate Teammate**:
- **Never Again** — permanent block, you'll never be grouped together
- **Best Buddy** — if they mark you back, you'll always be grouped together

---

**MESSAGE 3:**

## Other Commands

- `/stats lookup @player` — check another player's stats
- `/leaderboard` — server ADR rankings
- `/buddies` — see your confirmed buddy pairs
- `/unblock @player` — remove a block you placed
- `/queue` — your wait time, players needed, laxative countdown
- `/queuepref skill|fast` — choose tight skill matches or faster groups

## Rules

1. Your Discord nickname must match your PUBG name (set automatically on registration)
2. FPP only — squad-fpp and duo-fpp
3. PC/Steam only
4. Be respectful — use the feedback system, not chat drama
5. Don't idle in LFG lobbies if you're not ready to play
