CREATE TABLE ops_session (
    session_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date       TEXT NOT NULL UNIQUE,
    regime_read      TEXT NOT NULL DEFAULT '',
    harness_version  INTEGER,                 -- 软链(目标表 D 期建,不加 FK)
    decision_run_ref TEXT,                    -- 软链(目标表 C 期建,不加 FK)
    no_trade_reason  TEXT NOT NULL DEFAULT '',
    note             TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);
CREATE TABLE ops_candidate (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES ops_session(session_id),
    code         TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    pattern      TEXT NOT NULL DEFAULT '',
    rank         INTEGER NOT NULL,
    confidence   REAL NOT NULL DEFAULT 0.5,
    reason       TEXT NOT NULL DEFAULT '',
    plan_entry   REAL,
    plan_stop    REAL,
    plan_target  REAL,
    plan_note    TEXT NOT NULL DEFAULT '',
    raw          TEXT,
    UNIQUE(session_id, code)
);
CREATE TABLE ops_decision (
    decision_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES ops_session(session_id),
    candidate_id  INTEGER REFERENCES ops_candidate(candidate_id),
    code          TEXT NOT NULL,
    action        TEXT NOT NULL,
    intent_side   TEXT,
    planned_price REAL,
    planned_qty   INTEGER,
    status        TEXT NOT NULL DEFAULT 'planned',
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE ops_position (
    position_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL,
    name               TEXT NOT NULL DEFAULT '',
    pattern            TEXT NOT NULL DEFAULT '',
    opened_on          TEXT NOT NULL,
    closed_on          TEXT,
    status             TEXT NOT NULL DEFAULT 'open',
    qty_open           INTEGER NOT NULL DEFAULT 0,
    avg_cost           REAL NOT NULL DEFAULT 0,
    realized_pnl       REAL NOT NULL DEFAULT 0,
    origin_decision_id INTEGER REFERENCES ops_decision(decision_id)
);
CREATE TABLE ops_fill (
    fill_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER REFERENCES ops_decision(decision_id),
    position_id INTEGER REFERENCES ops_position(position_id),
    code        TEXT NOT NULL,
    side        TEXT NOT NULL,
    price       REAL NOT NULL,
    qty         INTEGER NOT NULL,
    filled_at   TEXT NOT NULL,
    fee         REAL,
    note        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE ops_review (
    review_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES ops_session(session_id),
    position_id INTEGER REFERENCES ops_position(position_id),
    body        TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    lesson_ref  TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE ops_account_daily (
    trade_date       TEXT PRIMARY KEY,
    equity           REAL,
    cash             REAL,
    market_value     REAL,
    realized_pnl_day REAL,
    unrealized_pnl   REAL,
    note             TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_candidate_session ON ops_candidate(session_id);
CREATE INDEX idx_decision_session ON ops_decision(session_id);
CREATE INDEX idx_fill_position ON ops_fill(position_id);
CREATE INDEX idx_position_code_status ON ops_position(code, status);
