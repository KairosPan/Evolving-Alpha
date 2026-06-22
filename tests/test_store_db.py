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
