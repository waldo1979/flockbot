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
    adr_season        TEXT,
    queue_preference  TEXT DEFAULT 'skill'
);

CREATE TABLE IF NOT EXISTS player_cache (
    pubg_id           TEXT PRIMARY KEY,
    pubg_name         TEXT NOT NULL,
    last_lookup       TEXT NOT NULL DEFAULT (datetime('now')),
    last_stats_update TEXT,
    squad_fpp_adr     REAL,
    squad_fpp_tier    TEXT,
    squad_fpp_matches INTEGER DEFAULT 0,
    duo_fpp_adr       REAL,
    duo_fpp_tier      TEXT,
    duo_fpp_matches   INTEGER DEFAULT 0,
    adr_season        TEXT
);

CREATE TABLE IF NOT EXISTS match_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pubg_id      TEXT NOT NULL,
    match_id     TEXT NOT NULL,
    game_mode    TEXT NOT NULL CHECK(game_mode IN ('squad-fpp', 'duo-fpp')),
    season       TEXT NOT NULL,
    damage_dealt REAL NOT NULL,
    kills        INTEGER NOT NULL,
    assists      INTEGER NOT NULL,
    win_place    INTEGER NOT NULL,
    match_date   TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(pubg_id, match_id)
);
CREATE INDEX IF NOT EXISTS idx_match_stats_player_mode
    ON match_stats(pubg_id, game_mode, season);

CREATE TABLE IF NOT EXISTS hangout_time (
    player_a     TEXT NOT NULL,
    player_b     TEXT NOT NULL,
    minutes      REAL NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_a, player_b),
    CHECK(player_a < player_b)
);
CREATE INDEX IF NOT EXISTS idx_hangout_time
    ON hangout_time(player_a, player_b);

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

