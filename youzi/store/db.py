# youzi/store/db.py
"""live.db 连接工厂 + schema 建表 + 版本戳。

库路径:环境变量 `YOUZI_LIVE_DB` 覆盖,默认 `<repo>/live.db`
(写法对齐 `youzi_web/data_access.py` 的 `YOUZI_RUNS_DIR`)。

**约束进 schema,不靠纪律**:唯一键/CHECK/外键全部写进 DDL,
Python 侧(repo)再做一遍——双侧强制,单侧被绕过也不会脏数据。

版本管理用 `PRAGMA user_version`(初版=1),**建表完成后最后打戳**:
中途崩溃 → user_version 仍是 0 → 下次启动重跑建表(CREATE IF NOT EXISTS 幂等),
不会出现"戳了版本但表没建全"的半初始化态。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from youzi.config import PROJECT_ROOT

SCHEMA_VERSION = 1

# agent_run 状态机取值(与 AgentRunRepository._ALLOWED 同源,DDL 侧 CHECK 兜底)
_RUN_STATUSES = ("pending", "running", "succeeded", "failed")

_DDL = f"""
CREATE TABLE IF NOT EXISTS agent_run (
    run_id               TEXT PRIMARY KEY,
    trade_date           TEXT NOT NULL,
    market_as_of         TEXT,
    snapshot_ref         TEXT,
    strategy_id          TEXT NOT NULL,
    harness_snapshot_ref TEXT,
    account_id           TEXT NOT NULL DEFAULT '',
    account_context_json TEXT,
    model                TEXT NOT NULL DEFAULT '',
    temperature          REAL,
    prompt_fingerprint   TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL
                         CHECK (status IN {_RUN_STATUSES}),
    raw_output           TEXT,
    parsed_output_json   TEXT,
    error                TEXT,
    created_at           TEXT NOT NULL,
    finished_at          TEXT,
    adopted_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_agent_run_date ON agent_run (trade_date);

CREATE TABLE IF NOT EXISTS ops_session (
    session_id   TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    trade_date   TEXT NOT NULL,
    agent_run_id TEXT NOT NULL REFERENCES agent_run (run_id),
    created_at   TEXT NOT NULL,
    UNIQUE (account_id, trade_date)
);

CREATE TABLE IF NOT EXISTS ops_candidate (
    candidate_id TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES ops_session (session_id) ON DELETE CASCADE,
    rank         INTEGER NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    pattern      TEXT NOT NULL DEFAULT '',
    score        REAL,
    reason       TEXT NOT NULL DEFAULT '',
    plan_json    TEXT,
    check_status TEXT NOT NULL
                 CHECK (check_status IN ('ok', 'blocked', 'unknown')),
    check_json   TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (session_id, code)
);
CREATE INDEX IF NOT EXISTS ix_ops_candidate_session ON ops_candidate (session_id);

CREATE TABLE IF NOT EXISTS decision (
    decision_id  TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES ops_session (session_id),
    candidate_id TEXT NOT NULL REFERENCES ops_candidate (candidate_id),
    action       TEXT NOT NULL CHECK (action IN ('buy', 'skip', 'watch')),
    note         TEXT NOT NULL DEFAULT '',
    confirmed_at TEXT NOT NULL,
    UNIQUE (candidate_id)
);

CREATE TABLE IF NOT EXISTS fill (
    fill_id      TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    account_id   TEXT NOT NULL,
    trade_date   TEXT NOT NULL,
    code         TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    price        REAL NOT NULL CHECK (price > 0),
    qty          INTEGER NOT NULL CHECK (qty > 0),
    fee          REAL NOT NULL DEFAULT 0.0 CHECK (fee >= 0),
    decision_id  TEXT REFERENCES decision (decision_id),
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fill_account ON fill (account_id, created_at);

CREATE TABLE IF NOT EXISTS account_snapshot (
    account_id     TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    cash           REAL NOT NULL,
    positions_json TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    PRIMARY KEY (account_id, as_of)
);
"""


def db_path() -> Path:
    """live.db 路径:`YOUZI_LIVE_DB` 覆盖,默认 `<repo>/live.db`。"""
    return Path(os.environ.get("YOUZI_LIVE_DB", str(PROJECT_ROOT / "live.db")))


def init_schema(conn: sqlite3.Connection) -> None:
    """建表(幂等)+ 打版本戳。库版本高于本代码 → 大声拒绝,不猜测兼容。"""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"live.db schema 版本 {current} 高于本代码支持的 {SCHEMA_VERSION};"
            "请升级代码,勿降级写入")
    with conn:
        conn.executescript(_DDL)
        # 建表全部成功后**最后**打戳(半初始化不会被误判为已就绪)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION:d}")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """打开(必要时创建)live.db,建好 schema 后返回连接。

    `:memory:` 亦可(测试用);WAL 对内存库自动降级为 memory 日志,不报错。
    `check_same_thread=False`:web 层每请求新建连接、且只在该请求内使用,
    但 ASGI 线程池可能换线程执行同一请求的同步端点,故放开线程校验。
    """
    p = Path(path) if path is not None else db_path()
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")       # 读写并发(单写多读),崩溃安全
    conn.execute("PRAGMA foreign_keys=ON")        # 外键默认关闭,必须显式开
    init_schema(conn)
    return conn
