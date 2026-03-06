CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS players (
    discord_id        TEXT PRIMARY KEY,
    pubg_id           TEXT UNIQUE,
    pubg_name         TEXT NOT NULL,
    registered_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_stats_update TEXT,
    squad_fpp_adr     REAL,
    squad_fpp_tier    TEXT,
    squad_fpp_matches INTEGER,
    duo_fpp_adr       REAL,
    duo_fpp_tier      TEXT,
    duo_fpp_matches   INTEGER,
    adr_season        TEXT
);

CREATE TABLE IF NOT EXISTS match_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id   TEXT NOT NULL REFERENCES players(discord_id),
    match_id     TEXT NOT NULL,
    game_mode    TEXT NOT NULL CHECK(game_mode IN ('squad-fpp', 'duo-fpp')),
    season       TEXT NOT NULL,
    damage_dealt REAL NOT NULL,
    kills        INTEGER NOT NULL,
    assists      INTEGER NOT NULL,
    win_place    INTEGER NOT NULL,
    match_date   TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(discord_id, match_id)
);
CREATE INDEX IF NOT EXISTS idx_match_stats_player_mode
    ON match_stats(discord_id, game_mode, season);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user  TEXT NOT NULL REFERENCES players(discord_id),
    to_user    TEXT NOT NULL REFERENCES players(discord_id),
    value      INTEGER NOT NULL CHECK(value IN (-1, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK(from_user != to_user)
);
CREATE INDEX IF NOT EXISTS idx_feedback_pair
    ON feedback(from_user, to_user, created_at);

CREATE TABLE IF NOT EXISTS blocks (
    from_user  TEXT NOT NULL REFERENCES players(discord_id),
    to_user    TEXT NOT NULL REFERENCES players(discord_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_user, to_user),
    CHECK(from_user != to_user)
);

CREATE TABLE IF NOT EXISTS buddies (
    from_user  TEXT NOT NULL REFERENCES players(discord_id),
    to_user    TEXT NOT NULL REFERENCES players(discord_id),
    confirmed  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_user, to_user),
    CHECK(from_user != to_user)
);

CREATE TABLE IF NOT EXISTS co_play_log (
    player_a TEXT NOT NULL,
    player_b TEXT NOT NULL,
    date     TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(player_a, player_b, date),
    CHECK(player_a < player_b)
);
CREATE INDEX IF NOT EXISTS idx_co_play
    ON co_play_log(player_a, player_b, date);
