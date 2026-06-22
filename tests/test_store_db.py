from youzi.store.db import Database


def test_fresh_db_version_zero_and_truthy():
    db = Database(":memory:")
    assert db.version == 0
    assert bool(db) is True
    db.close()


def test_foreign_keys_enabled():
    db = Database(":memory:")
    row = db.query_one("PRAGMA foreign_keys")
    assert row[0] == 1
    db.close()


def test_wal_on_file_db(tmp_path):
    db = Database(tmp_path / "youzi.db")
    row = db.query_one("PRAGMA journal_mode")
    assert row[0].lower() == "wal"
    db.close()


_OPS_TABLES = {
    "ops_session", "ops_candidate", "ops_decision",
    "ops_position", "ops_fill", "ops_review", "ops_account_daily",
}


def _table_names(db):
    rows = db.query_all("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


def test_migrate_creates_ops_tables_and_bumps_version():
    db = Database(":memory:")
    applied = db.migrate()
    assert applied == 1
    assert db.version == 1
    assert _OPS_TABLES.issubset(_table_names(db))
    db.close()


def test_migrate_is_idempotent():
    db = Database(":memory:")
    db.migrate()
    assert db.migrate() == 0          # 第二次无 pending
    assert db.version == 1
    db.close()
