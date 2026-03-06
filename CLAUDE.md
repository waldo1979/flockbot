# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flockbot is a Discord bot for PUBG (PC/Steam) squad/duo formation. It matches players using skill level (ADR from the PUBG API) and social compatibility (peer feedback with exponential decay). Players queue by joining voice channel lobbies; the bot forms groups and moves them into temporary voice channels.

The formal specification lives in `spec/flockbot.md` — that is the source of truth for all design decisions.

## Stack

- Python 3.11+ / discord.py 2.4+ (slash commands via `app_commands`)
- SQLite via aiosqlite (WAL mode) — database at `data/flockbot.db`
- aiohttp for PUBG API calls
- uv for dependency management (`pyproject.toml` + `uv.lock`)
- Docker for deployment

## Commands

```bash
uv sync                                      # Install dependencies
uv run python bot.py                         # Run the bot
uv run pytest tests/ -v                      # Run all tests
uv run pytest tests/test_matchmaker.py -v    # Run a single test file
docker compose build                         # Build container
docker compose up -d                         # Run containerized
```

## Key Conventions

- All database operations use aiosqlite (async). Never use synchronous sqlite3.
- All Discord interactions use slash commands (`app_commands`), not prefix commands.
- Cogs use `@app_commands.command()` inside `commands.Cog` subclasses.
- Cogs are loaded via `bot.load_extension("commands.stats")` in `setup_hook`. Every cog file must have an `async def setup(bot)` function.
- Use ephemeral responses for personal data (scores, feedback). Use public embeds for leaderboards and announcements.
- FPP only: only `squad-fpp` and `duo-fpp` game modes are tracked. TPP is ignored entirely.
- ADR is mode-specific and season-aware. Fallback: current season (≥10 matches) → previous season → "New".
- ADR tiers use numeric labels (`<100`, `100+`, `200+`, `250+`, `300+`, `400+`), never metals (gold/silver/bronze) and never "unranked" (PUBG-specific term).
- PUBG API rate limit: 10 req/min for `/players` and `/seasons`. `/matches/{id}` and telemetry are exempt.
- Feedback decay: 100% (0-2wk), 75% (2-4wk), 50% (4-6wk), 25% (6-8wk), 0% (>8wk). Raw entries deleted after 84 days.
- Blocks ("Never Again") and buddy bonds are permanent — never decayed or cleaned up.
- Queue state is in-memory only (derived from voice channel presence). No persistent queue table.
- Timestamps in SQLite use ISO-8601 format: `datetime('now')` in SQL, `.isoformat()` in Python.

## Architecture

- `bot.py` — Entry point. `FlockBot(commands.Bot)` subclass with `setup_hook` and graceful shutdown.
- `config.py` — Loads `.env`, exposes typed constants.
- `commands/` — Discord slash command cogs (admin, stats, feedback, queue).
- `events/` — Discord event listeners (on_ready, lfg_handler, voice_tracker).
- `services/` — Business logic (pubg_api, stats_service, feedback_service, matchmaker).
- `database/` — Data access layer (connection, schema.sql, *_repo.py files).
- `utils/` — Shared utilities (embeds, rate_limiter, time_helpers, views).

## Environment Variables

- `DISCORD_TOKEN` — Bot token from Discord Developer Portal
- `PUBG_API_KEY` — API key from developer.pubg.com
- `DATABASE_PATH` — SQLite file path (default: `data/flockbot.db`)
- `GUILD_ID` — Optional dev guild for instant slash command sync
