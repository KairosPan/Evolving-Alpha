from __future__ import annotations

import importlib.resources
import re
import sqlite3
from pathlib import Path

_MIG_RE = re.compile(r"^(\d+)_.*\.sql$")


class Database:
    """单机 SQLite 连接壳:WAL + 外键 + schema_meta 版本表。沿用项目容器约定 __bool__=True。"""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        is_memory = self._path == ":memory:"
        if not is_memory:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        if not is_memory:
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
        if self._conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0] == 0:
            self._conn.execute("INSERT INTO schema_meta (version) VALUES (0)")
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def version(self) -> int:
        return self._conn.execute("SELECT version FROM schema_meta").fetchone()[0]

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __bool__(self) -> bool:
        return True

    def _discover_migrations(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for entry in importlib.resources.files("youzi.store.migrations").iterdir():
            m = _MIG_RE.match(entry.name)
            if m:
                out.append((int(m.group(1)), entry.read_text(encoding="utf-8")))
        return sorted(out, key=lambda t: t[0])

    def migrate(self) -> int:
        cur = self.version
        applied = 0
        for n, sql in self._discover_migrations():
            if n <= cur:
                continue
            self._conn.executescript(sql)
            self._conn.execute("UPDATE schema_meta SET version=?", (n,))
            self._conn.commit()
            applied += 1
        return applied
