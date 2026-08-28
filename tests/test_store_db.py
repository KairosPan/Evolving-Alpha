# tests/test_store_db.py
"""live.db 连接/schema/版本戳。"""
import sqlite3

import pytest

from youzi.store.db import SCHEMA_VERSION, connect, db_path, init_schema

_TABLES = {"agent_run", "ops_session", "ops_candidate", "decision", "fill",
           "account_snapshot"}


def _tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def test_connect_creates_all_tables_and_stamps_version(tmp_path):
    conn = connect(tmp_path / "live.db")
    assert _TABLES <= _tables(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_connect_is_idempotent(tmp_path):
    p = tmp_path / "live.db"
    connect(p).close()
    conn = connect(p)                      # 重开不该重建/报错
    assert _TABLES <= _tables(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_wal_and_foreign_keys_on(tmp_path):
    conn = connect(tmp_path / "live.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_future_schema_version_is_rejected(tmp_path):
    """库版本高于代码 → 大声拒绝,不猜测兼容(防降级写入毁数据)。"""
    p = tmp_path / "live.db"
    conn = sqlite3.connect(str(p))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    with pytest.raises(RuntimeError, match="高于本代码"):
        init_schema(conn)


def test_db_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUZI_LIVE_DB", str(tmp_path / "custom.db"))
    assert db_path() == tmp_path / "custom.db"
    monkeypatch.delenv("YOUZI_LIVE_DB")
    assert db_path().name == "live.db"      # 默认落 <repo>/live.db


def test_fill_check_constraints_are_in_schema(tmp_path):
    """约束进 schema 不靠纪律:非法 side / 非正价量在 SQL 侧就被拒。"""
    conn = connect(tmp_path / "live.db")
    base = ("INSERT INTO fill (fill_id, operation_id, account_id, trade_date, code,"
            " side, price, qty, fee, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base, ("f1", "o1", "A", "2024-06-26", "600000", "short",
                            10.0, 100, 0.0, "t"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base, ("f2", "o2", "A", "2024-06-26", "600000", "buy",
                            0.0, 100, 0.0, "t"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base, ("f3", "o3", "A", "2024-06-26", "600000", "buy",
                            10.0, 0, 0.0, "t"))


def test_agent_run_status_check_constraint(tmp_path):
    conn = connect(tmp_path / "live.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO agent_run (run_id, trade_date, strategy_id, status, created_at)"
            " VALUES ('r','2024-06-26','s','bogus','t')")
