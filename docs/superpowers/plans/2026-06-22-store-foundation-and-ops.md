# Store 地基 + 运营全闭环(A + B-domain)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建 `youzi/store/` 包:SQLite 连接壳 + 迁移机制(A 期),以及运营全闭环领域层——7 张表、pydantic 模型、纯函数盈亏服务、`OpsRepository` 命令/查询 API(B-domain 期)。全离线可测,不含 web。

**Architecture:** 单库单文件(`YOUZI_DB`,默认 `./data/youzi.db`),薄 Repository 手写 SQL 映射 `pydantic ⇄ 行`,沿用现有 `RunStore`/`PITStore` 容器风格。盈亏结算是 `account.py` 纯函数(不进 SQL trigger,保持可测)。运营数据是 SQLite 当真相源的前向交易日志。

**Tech Stack:** Python 3.12 · 标准库 `sqlite3`(零新依赖)· `pydantic` v2 · `pytest`。

## Global Constraints

(每个任务的要求都隐含包含本节,值逐字抄自 spec `docs/superpowers/specs/2026-06-22-sqlite-data-model-design.md`)

- **零新依赖**:只用标准库 `sqlite3`,不引 SQLModel/SQLAlchemy/Alembic/ORM。
- **离线优先**:所有测试用 `Database(":memory:")` 或 tmp 文件,永不触网;现有 466 测试保持全绿。
- **缺失值诚实 `None`**:没填的计划价/费/名 → `None`,绝不臆造 `0`/`""`。
- **容器 `__bool__ = True`**:`Database`/`OpsRepository` 都要,杀 falsy-empty 陷阱。
- **pydantic 约定**:运营行模型可变(代表可变行),用普通 `BaseModel`;不混入 frozen。
- **日期/时间存 ISO `TEXT`**:`date` 存 `YYYY-MM-DD`,`datetime` 存 ISO 字符串;读回在 Repository 层归一为 `date`/`datetime` 对象。
- **确定性时间**:`OpsRepository` 取 `clock: Callable[[], datetime]` 注入(默认 `datetime.now`),测试注入固定时钟。
- **盈亏逻辑只在 Python**:`account.py` 纯函数,不写 SQL trigger。
- **防火墙(本期不碰但守住)**:`youzi/store/` 是领域持久化,决策路径不引用它;本期不触 agent/policy/SnapshotSource。

---

## 文件结构

```
youzi/store/
  __init__.py                  # 导出 Database / OpsRepository / 模型
  db.py                        # Database:sqlite3 连接 + WAL + FK + 迁移 runner + schema_meta
  migrations/
    __init__.py                # 包标记(空)
    001_ops_tables.sql         # 7 张运营表 DDL + 索引
  models.py                    # OpsSession/Candidate/Decision/Fill/Position/Review/AccountDaily
  account.py                   # PositionState + apply_buy/apply_sell 纯函数
  ops_repo.py                  # OpsRepository:会话/候选/决策/成交/持仓/复盘/账户/分析
tests/
  test_store_db.py             # Database + 迁移
  test_store_models.py         # 模型默认/None
  test_store_account.py        # 盈亏纯函数
  test_ops_repo.py             # Repository(逐任务增长 + 末尾全生命周期集成)
```

---

## Task 1: Database 连接壳 + schema_meta 引导

**Files:**
- Create: `youzi/store/__init__.py`
- Create: `youzi/store/db.py`
- Test: `tests/test_store_db.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `class Database` with `__init__(self, path: str | Path)`、`version: int`(property)、`execute(sql: str, params: tuple = ()) -> sqlite3.Cursor`、`query_one(sql, params=()) -> sqlite3.Row | None`、`query_all(sql, params=()) -> list[sqlite3.Row]`、`commit() -> None`、`close() -> None`、`conn: sqlite3.Connection`(property)、`__enter__/__exit__`、`__bool__ -> True`。
  - `version` 初始为 `0`;构造即建 `schema_meta(version INTEGER NOT NULL)` 单行表。
  - 连接设 `row_factory = sqlite3.Row`、`PRAGMA foreign_keys=ON`;文件库设 `PRAGMA journal_mode=WAL`(`:memory:` 不设/不断言 WAL)。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_db.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'youzi.store'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/__init__.py
from youzi.store.db import Database

__all__ = ["Database"]
```

```python
# youzi/store/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path


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

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_store_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/__init__.py youzi/store/db.py tests/test_store_db.py
git commit -m "feat(store): Database 连接壳 + schema_meta(WAL/FK/版本表)"
```

---

## Task 2: 迁移 runner + 001 运营表 DDL

**Files:**
- Create: `youzi/store/migrations/__init__.py`
- Create: `youzi/store/migrations/001_ops_tables.sql`
- Modify: `youzi/store/db.py`(加 `migrate()` + `_discover_migrations()`)
- Test: `tests/test_store_db.py`(追加)

**Interfaces:**
- Consumes: `Database`(Task 1)。
- Produces: `Database.migrate() -> int`(应用所有 version > 当前 的 `migrations/NNN_*.sql`,按 N 升序,逐个 `executescript` 后 `UPDATE schema_meta`,返回应用条数;重复调用幂等返回 0)。迁移 001 后存在 7 张表:`ops_session`、`ops_candidate`、`ops_decision`、`ops_position`、`ops_fill`、`ops_review`、`ops_account_daily`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_db.py (追加)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store_db.py -k migrate -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'migrate'`

- [ ] **Step 3: Write minimal implementation**

```sql
-- youzi/store/migrations/001_ops_tables.sql
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
```

```python
# youzi/store/migrations/__init__.py
# 迁移 SQL 包(NNN_*.sql 按序幂等应用)
```

```python
# youzi/store/db.py —— 顶部 import 追加
import importlib.resources
import re

_MIG_RE = re.compile(r"^(\d+)_.*\.sql$")
```

```python
# youzi/store/db.py —— Database 类内追加方法
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_store_db.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/migrations youzi/store/db.py tests/test_store_db.py
git commit -m "feat(store): 迁移 runner + 001 运营表 DDL(7 表 + 索引)"
```

---

## Task 3: 运营域 pydantic 模型

**Files:**
- Create: `youzi/store/models.py`
- Modify: `youzi/store/__init__.py`(导出模型)
- Test: `tests/test_store_models.py`

**Interfaces:**
- Consumes: 无。
- Produces(全部 `pydantic.BaseModel`,主键/`created_at` 默认 `None`,缺失值 `None`):
  - `OpsSession(session_id, trade_date: date, regime_read='', harness_version: int|None, decision_run_ref: str|None, no_trade_reason='', note='', created_at: datetime|None)`
  - `OpsCandidate(candidate_id, session_id: int, code, name='', pattern='', rank: int, confidence=0.5, reason='', plan_entry/plan_stop/plan_target: float|None, plan_note='', raw: dict|None)`
  - `OpsDecision(decision_id, session_id: int, candidate_id: int|None, code, action, intent_side: str|None, planned_price: float|None, planned_qty: int|None, status='planned', note='', created_at: datetime|None)`
  - `OpsFill(fill_id, decision_id: int|None, position_id: int|None, code, side, price: float, qty: int, filled_at: datetime, fee: float|None, note='')`
  - `OpsPosition(position_id, code, name='', pattern='', opened_on: date, closed_on: date|None, status='open', qty_open=0, avg_cost=0.0, realized_pnl=0.0, origin_decision_id: int|None)`
  - `OpsReview(review_id, session_id: int|None, position_id: int|None, body='', tags='', lesson_ref: str|None, created_at: datetime|None)`
  - `AccountDaily(trade_date: date, equity/cash/market_value/realized_pnl_day/unrealized_pnl: float|None, note='')`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_models.py
from datetime import date, datetime

from youzi.store.models import (
    AccountDaily, OpsCandidate, OpsDecision, OpsFill,
    OpsPosition, OpsReview, OpsSession,
)


def test_session_defaults_and_honest_none():
    s = OpsSession(trade_date=date(2026, 6, 22))
    assert s.session_id is None
    assert s.regime_read == ""
    assert s.harness_version is None        # 缺失诚实 None,不臆造 0
    assert s.decision_run_ref is None


def test_candidate_plan_prices_optional():
    c = OpsCandidate(session_id=1, code="600519", rank=1)
    assert c.confidence == 0.5
    assert c.plan_entry is None and c.plan_stop is None and c.plan_target is None
    assert c.raw is None


def test_fill_requires_price_qty_filled_at():
    f = OpsFill(code="600519", side="buy", price=10.0, qty=100,
               filled_at=datetime(2026, 6, 23, 9, 30))
    assert f.fee is None                    # 没填费 → None
    assert f.position_id is None


def test_position_and_review_and_account_defaults():
    p = OpsPosition(code="600519", opened_on=date(2026, 6, 23))
    assert p.status == "open" and p.qty_open == 0 and p.realized_pnl == 0.0
    r = OpsReview()
    assert r.session_id is None and r.position_id is None and r.lesson_ref is None
    a = AccountDaily(trade_date=date(2026, 6, 23))
    assert a.equity is None and a.unrealized_pnl is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'youzi.store.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/models.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, Field


class OpsSession(BaseModel):
    session_id: int | None = None
    trade_date: Date
    regime_read: str = ""
    harness_version: int | None = None       # 软链(D 期)
    decision_run_ref: str | None = None       # 软链(C 期)
    no_trade_reason: str = ""
    note: str = ""
    created_at: DateTime | None = None


class OpsCandidate(BaseModel):
    candidate_id: int | None = None
    session_id: int
    code: str
    name: str = ""
    pattern: str = ""
    rank: int
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""
    plan_entry: float | None = None
    plan_stop: float | None = None
    plan_target: float | None = None
    plan_note: str = ""
    raw: dict | None = None


class OpsDecision(BaseModel):
    decision_id: int | None = None
    session_id: int
    candidate_id: int | None = None
    code: str
    action: str                              # confirm | skip | manual_add | modify
    intent_side: str | None = None           # buy | sell
    planned_price: float | None = None
    planned_qty: int | None = None
    status: str = "planned"                   # planned | executed | cancelled | expired
    note: str = ""
    created_at: DateTime | None = None


class OpsFill(BaseModel):
    fill_id: int | None = None
    decision_id: int | None = None
    position_id: int | None = None
    code: str
    side: str                                 # buy | sell
    price: float
    qty: int
    filled_at: DateTime
    fee: float | None = None
    note: str = ""


class OpsPosition(BaseModel):
    position_id: int | None = None
    code: str
    name: str = ""
    pattern: str = ""
    opened_on: Date
    closed_on: Date | None = None
    status: str = "open"                      # open | closed
    qty_open: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    origin_decision_id: int | None = None


class OpsReview(BaseModel):
    review_id: int | None = None
    session_id: int | None = None
    position_id: int | None = None
    body: str = ""
    tags: str = ""
    lesson_ref: str | None = None
    created_at: DateTime | None = None


class AccountDaily(BaseModel):
    trade_date: Date
    equity: float | None = None
    cash: float | None = None
    market_value: float | None = None
    realized_pnl_day: float | None = None
    unrealized_pnl: float | None = None
    note: str = ""
```

```python
# youzi/store/__init__.py —— 替换为
from youzi.store.db import Database
from youzi.store.models import (
    AccountDaily, OpsCandidate, OpsDecision, OpsFill,
    OpsPosition, OpsReview, OpsSession,
)

__all__ = [
    "Database", "OpsSession", "OpsCandidate", "OpsDecision",
    "OpsFill", "OpsPosition", "OpsReview", "AccountDaily",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_store_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/models.py youzi/store/__init__.py tests/test_store_models.py
git commit -m "feat(store): 运营域 pydantic 模型(7 个,缺失诚实 None)"
```

---

## Task 4: account.py 盈亏结算纯函数

**Files:**
- Create: `youzi/store/account.py`
- Test: `tests/test_store_account.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `@dataclass class PositionState(qty_open: int, avg_cost: float, realized_pnl: float, status: str)`
  - `EMPTY_POSITION: PositionState`(`qty_open=0, avg_cost=0.0, realized_pnl=0.0, status="open"`)
  - `apply_buy(state: PositionState, price: float, qty: int, fee: float | None = None) -> PositionState`
  - `apply_sell(state: PositionState, price: float, qty: int, fee: float | None = None) -> PositionState`(`qty > state.qty_open` → `ValueError`;归零 → `status="closed"`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_account.py
import pytest

from youzi.store.account import EMPTY_POSITION, apply_buy, apply_sell


def test_buy_sets_avg_cost_including_fee():
    s = apply_buy(EMPTY_POSITION, price=10.0, qty=100, fee=5.0)
    assert s.qty_open == 100
    assert s.avg_cost == pytest.approx((10.0 * 100 + 5.0) / 100)   # 10.05
    assert s.status == "open"


def test_batched_buys_weighted_average():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)          # fee 缺省 None → 0
    s = apply_buy(s, 12.0, 100)
    assert s.qty_open == 200
    assert s.avg_cost == pytest.approx(11.0)


def test_sell_realizes_pnl_and_closes_on_zero():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    s = apply_sell(s, price=12.0, qty=100, fee=3.0)
    assert s.qty_open == 0
    assert s.realized_pnl == pytest.approx((12.0 - 10.0) * 100 - 3.0)  # 197.0
    assert s.status == "closed"


def test_partial_sell_keeps_open():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    s = apply_sell(s, 11.0, 40)
    assert s.qty_open == 60
    assert s.status == "open"
    assert s.realized_pnl == pytest.approx((11.0 - 10.0) * 40)


def test_oversell_raises():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    with pytest.raises(ValueError):
        apply_sell(s, 11.0, 101)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_store_account.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'youzi.store.account'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/account.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionState:
    qty_open: int
    avg_cost: float
    realized_pnl: float
    status: str            # open | closed


EMPTY_POSITION = PositionState(qty_open=0, avg_cost=0.0, realized_pnl=0.0, status="open")


def apply_buy(state: PositionState, price: float, qty: int,
              fee: float | None = None) -> PositionState:
    fee = fee or 0.0
    new_qty = state.qty_open + qty
    new_cost = (state.avg_cost * state.qty_open + price * qty + fee) / new_qty
    return PositionState(qty_open=new_qty, avg_cost=new_cost,
                         realized_pnl=state.realized_pnl, status="open")


def apply_sell(state: PositionState, price: float, qty: int,
               fee: float | None = None) -> PositionState:
    if qty > state.qty_open:
        raise ValueError(f"卖出 {qty} 超过持仓 {state.qty_open}")
    fee = fee or 0.0
    pnl = (price - state.avg_cost) * qty - fee
    new_qty = state.qty_open - qty
    return PositionState(qty_open=new_qty, avg_cost=state.avg_cost,
                         realized_pnl=state.realized_pnl + pnl,
                         status="closed" if new_qty == 0 else "open")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_store_account.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/account.py tests/test_store_account.py
git commit -m "feat(store): account.py 盈亏结算纯函数(均价/实现盈亏/平仓)"
```

---

## Task 5: OpsRepository — 会话 + 候选

**Files:**
- Create: `youzi/store/ops_repo.py`
- Modify: `youzi/store/__init__.py`(导出 `OpsRepository`)
- Test: `tests/test_ops_repo.py`

**Interfaces:**
- Consumes: `Database`(Task 1/2)、模型(Task 3)。
- Produces:
  - `class OpsRepository(db: Database, clock: Callable[[], datetime] = datetime.now)`;`__bool__ -> True`。
  - `create_session(s: OpsSession) -> OpsSession`(插入,回填 `session_id` + `created_at`;`created_at` 为 None 时用 `clock()`)
  - `get_session(session_id: int) -> OpsSession | None`
  - `session_for_date(trade_date: date) -> OpsSession | None`
  - `list_sessions(limit: int = 50) -> list[OpsSession]`(按 `trade_date` 倒序)
  - `add_candidates(session_id: int, cands: list[OpsCandidate]) -> list[OpsCandidate]`(批量插入,回填 `candidate_id`)
  - `candidates_for(session_id: int) -> list[OpsCandidate]`(按 `rank` 升序)
  - 内部 helper:`_iso(d)`/`_parse_date`/`_parse_dt`/`_row_to_session`/`_row_to_candidate`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ops_repo.py
from datetime import date, datetime

import pytest

from youzi.store.db import Database
from youzi.store.models import OpsCandidate, OpsSession
from youzi.store.ops_repo import OpsRepository

FIXED = datetime(2026, 6, 22, 8, 0, 0)


@pytest.fixture
def repo():
    db = Database(":memory:")
    db.migrate()
    yield OpsRepository(db, clock=lambda: FIXED)
    db.close()


def test_create_and_get_session(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22), regime_read="主升"))
    assert s.session_id is not None
    assert s.created_at == FIXED
    got = repo.get_session(s.session_id)
    assert got.trade_date == date(2026, 6, 22)
    assert got.regime_read == "主升"


def test_session_for_date_and_list(repo):
    repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    repo.create_session(OpsSession(trade_date=date(2026, 6, 23)))
    assert repo.session_for_date(date(2026, 6, 23)) is not None
    listed = repo.list_sessions()
    assert [s.trade_date for s in listed] == [date(2026, 6, 23), date(2026, 6, 22)]


def test_add_and_read_candidates_ordered_by_rank(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=2, pattern="首板"),
        OpsCandidate(session_id=s.session_id, code="000001", rank=1, pattern="连板"),
    ])
    cands = repo.candidates_for(s.session_id)
    assert [c.code for c in cands] == ["000001", "600519"]
    assert cands[0].candidate_id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'youzi.store.ops_repo'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/ops_repo.py
from __future__ import annotations

import json
from datetime import date as Date, datetime as DateTime
from typing import Callable

from youzi.store.db import Database
from youzi.store.models import OpsCandidate, OpsSession


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


def _parse_date(s: str | None) -> Date | None:
    return Date.fromisoformat(s) if s else None


def _parse_dt(s: str | None) -> DateTime | None:
    return DateTime.fromisoformat(s) if s else None


class OpsRepository:
    """运营全闭环 Repository:会话/候选/决策/成交/持仓/复盘/账户/分析。沿用容器约定 __bool__=True。"""

    def __init__(self, db: Database, clock: Callable[[], DateTime] = DateTime.now) -> None:
        self._db = db
        self._clock = clock

    def __bool__(self) -> bool:
        return True

    # ── 会话 ──
    def create_session(self, s: OpsSession) -> OpsSession:
        created = s.created_at or self._clock()
        cur = self._db.execute(
            "INSERT INTO ops_session (trade_date, regime_read, harness_version, "
            "decision_run_ref, no_trade_reason, note, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (_iso(s.trade_date), s.regime_read, s.harness_version, s.decision_run_ref,
             s.no_trade_reason, s.note, _iso(created)))
        self._db.commit()
        return s.model_copy(update={"session_id": cur.lastrowid, "created_at": created})

    def get_session(self, session_id: int) -> OpsSession | None:
        row = self._db.query_one(
            "SELECT * FROM ops_session WHERE session_id=?", (session_id,))
        return self._row_to_session(row) if row else None

    def session_for_date(self, trade_date: Date) -> OpsSession | None:
        row = self._db.query_one(
            "SELECT * FROM ops_session WHERE trade_date=?", (_iso(trade_date),))
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[OpsSession]:
        rows = self._db.query_all(
            "SELECT * FROM ops_session ORDER BY trade_date DESC LIMIT ?", (limit,))
        return [self._row_to_session(r) for r in rows]

    # ── 候选 ──
    def add_candidates(self, session_id: int,
                       cands: list[OpsCandidate]) -> list[OpsCandidate]:
        out: list[OpsCandidate] = []
        for c in cands:
            cur = self._db.execute(
                "INSERT INTO ops_candidate (session_id, code, name, pattern, rank, "
                "confidence, reason, plan_entry, plan_stop, plan_target, plan_note, raw) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, c.code, c.name, c.pattern, c.rank, c.confidence, c.reason,
                 c.plan_entry, c.plan_stop, c.plan_target, c.plan_note,
                 json.dumps(c.raw, ensure_ascii=False) if c.raw is not None else None))
            out.append(c.model_copy(update={"candidate_id": cur.lastrowid,
                                            "session_id": session_id}))
        self._db.commit()
        return out

    def candidates_for(self, session_id: int) -> list[OpsCandidate]:
        rows = self._db.query_all(
            "SELECT * FROM ops_candidate WHERE session_id=? ORDER BY rank ASC",
            (session_id,))
        return [self._row_to_candidate(r) for r in rows]

    # ── row → model ──
    def _row_to_session(self, r) -> OpsSession:
        return OpsSession(
            session_id=r["session_id"], trade_date=_parse_date(r["trade_date"]),
            regime_read=r["regime_read"], harness_version=r["harness_version"],
            decision_run_ref=r["decision_run_ref"], no_trade_reason=r["no_trade_reason"],
            note=r["note"], created_at=_parse_dt(r["created_at"]))

    def _row_to_candidate(self, r) -> OpsCandidate:
        return OpsCandidate(
            candidate_id=r["candidate_id"], session_id=r["session_id"], code=r["code"],
            name=r["name"], pattern=r["pattern"], rank=r["rank"],
            confidence=r["confidence"], reason=r["reason"], plan_entry=r["plan_entry"],
            plan_stop=r["plan_stop"], plan_target=r["plan_target"], plan_note=r["plan_note"],
            raw=json.loads(r["raw"]) if r["raw"] else None)
```

```python
# youzi/store/__init__.py —— 追加导出
from youzi.store.ops_repo import OpsRepository
# 并把 "OpsRepository" 加进 __all__
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/ops_repo.py youzi/store/__init__.py tests/test_ops_repo.py
git commit -m "feat(store): OpsRepository 会话 + 候选(增/查/排序)"
```

---

## Task 6: OpsRepository — 决策命令 API

**Files:**
- Modify: `youzi/store/ops_repo.py`(加决策方法 + `_row_to_decision`;import 追加 `OpsDecision`)
- Test: `tests/test_ops_repo.py`(追加)

**Interfaces:**
- Consumes: Task 5 的 `OpsRepository`、`OpsDecision`(Task 3)。
- Produces:
  - `confirm_decision(session_id, candidate_id, *, intent_side, planned_price=None, planned_qty=None, note="") -> OpsDecision`(action=`confirm`,从候选取 `code`)
  - `skip_candidate(session_id, candidate_id, *, note="") -> OpsDecision`(action=`skip`,status=`cancelled`)
  - `manual_add(session_id, code, *, intent_side, planned_price=None, planned_qty=None, note="") -> OpsDecision`(action=`manual_add`,candidate_id=None)
  - `decisions_for(session_id) -> list[OpsDecision]`
  - `_insert_decision(d: OpsDecision) -> OpsDecision`(内部:插入回填 id + created_at)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ops_repo.py (追加)
from youzi.store.models import OpsDecision  # 顶部已有则免


def _session_with_candidate(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    [c] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=1, pattern="首板")])
    return s, c


def test_confirm_decision_pulls_code_from_candidate(repo):
    s, c = _session_with_candidate(repo)
    d = repo.confirm_decision(s.session_id, c.candidate_id,
                              intent_side="buy", planned_price=10.0, planned_qty=100)
    assert d.decision_id is not None
    assert d.action == "confirm" and d.code == "600519"
    assert d.intent_side == "buy" and d.status == "planned"
    assert d.created_at == FIXED


def test_skip_marks_cancelled(repo):
    s, c = _session_with_candidate(repo)
    d = repo.skip_candidate(s.session_id, c.candidate_id, note="情绪退潮")
    assert d.action == "skip" and d.status == "cancelled"


def test_manual_add_has_no_candidate(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    d = repo.manual_add(s.session_id, "000001", intent_side="buy")
    assert d.candidate_id is None and d.code == "000001" and d.action == "manual_add"
    assert [x.decision_id for x in repo.decisions_for(s.session_id)] == [d.decision_id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -k "confirm or skip or manual" -v`
Expected: FAIL — `AttributeError: 'OpsRepository' object has no attribute 'confirm_decision'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/ops_repo.py —— import 追加 OpsDecision
from youzi.store.models import OpsCandidate, OpsDecision, OpsSession
```

```python
# youzi/store/ops_repo.py —— OpsRepository 内追加(放在候选方法之后)
    # ── 决策命令 API ──
    def _insert_decision(self, d: OpsDecision) -> OpsDecision:
        created = d.created_at or self._clock()
        cur = self._db.execute(
            "INSERT INTO ops_decision (session_id, candidate_id, code, action, "
            "intent_side, planned_price, planned_qty, status, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d.session_id, d.candidate_id, d.code, d.action, d.intent_side,
             d.planned_price, d.planned_qty, d.status, d.note, _iso(created)))
        self._db.commit()
        return d.model_copy(update={"decision_id": cur.lastrowid, "created_at": created})

    def confirm_decision(self, session_id: int, candidate_id: int, *, intent_side: str,
                         planned_price: float | None = None,
                         planned_qty: int | None = None, note: str = "") -> OpsDecision:
        row = self._db.query_one(
            "SELECT code FROM ops_candidate WHERE candidate_id=?", (candidate_id,))
        if row is None:
            raise ValueError(f"候选 {candidate_id} 不存在")
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=candidate_id, code=row["code"],
            action="confirm", intent_side=intent_side, planned_price=planned_price,
            planned_qty=planned_qty, status="planned", note=note))

    def skip_candidate(self, session_id: int, candidate_id: int, *,
                       note: str = "") -> OpsDecision:
        row = self._db.query_one(
            "SELECT code FROM ops_candidate WHERE candidate_id=?", (candidate_id,))
        if row is None:
            raise ValueError(f"候选 {candidate_id} 不存在")
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=candidate_id, code=row["code"],
            action="skip", status="cancelled", note=note))

    def manual_add(self, session_id: int, code: str, *, intent_side: str,
                   planned_price: float | None = None, planned_qty: int | None = None,
                   note: str = "") -> OpsDecision:
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=None, code=code, action="manual_add",
            intent_side=intent_side, planned_price=planned_price,
            planned_qty=planned_qty, status="planned", note=note))

    def decisions_for(self, session_id: int) -> list[OpsDecision]:
        rows = self._db.query_all(
            "SELECT * FROM ops_decision WHERE session_id=? ORDER BY decision_id ASC",
            (session_id,))
        return [self._row_to_decision(r) for r in rows]

    def _row_to_decision(self, r) -> OpsDecision:
        return OpsDecision(
            decision_id=r["decision_id"], session_id=r["session_id"],
            candidate_id=r["candidate_id"], code=r["code"], action=r["action"],
            intent_side=r["intent_side"], planned_price=r["planned_price"],
            planned_qty=r["planned_qty"], status=r["status"], note=r["note"],
            created_at=_parse_dt(r["created_at"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/ops_repo.py tests/test_ops_repo.py
git commit -m "feat(store): OpsRepository 决策命令 API(confirm/skip/manual_add)"
```

---

## Task 7: OpsRepository — 成交 + 持仓维护(盈亏落库)

**Files:**
- Modify: `youzi/store/ops_repo.py`(加 `record_fill`/持仓查询 + `_row_to_position`;import 追加 `OpsFill`/`OpsPosition` + `account`)
- Test: `tests/test_ops_repo.py`(追加)

**Interfaces:**
- Consumes: Task 5/6 的 `OpsRepository`、`OpsFill`/`OpsPosition`(Task 3)、`account`(Task 4)。
- Produces:
  - `record_fill(fill: OpsFill) -> tuple[OpsFill, OpsPosition]`:
    - 买入且该 `code` 无 open 持仓 → 新建持仓(`opened_on=fill.filled_at.date()`,`pattern` 取关联决策的候选 pattern,可空);否则取该 code 的 open 持仓。
    - 经 `account.apply_buy/apply_sell` 更新持仓 `qty_open/avg_cost/realized_pnl/status/closed_on`。
    - 插入 fill(回填 `fill_id` + `position_id`);若 `fill.decision_id` 非空 → 该决策 `status='executed'`。
    - 卖出但无 open 持仓 → `ValueError`。
  - `get_position(position_id) -> OpsPosition | None`
  - `open_position_for(code) -> OpsPosition | None`
  - `positions(status: str | None = None) -> list[OpsPosition]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ops_repo.py (追加)
from youzi.store.models import OpsFill


def test_buy_fill_opens_position(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    fill, pos = repo.record_fill(OpsFill(
        code="600519", side="buy", price=10.0, qty=100,
        filled_at=datetime(2026, 6, 23, 9, 30), fee=5.0))
    assert fill.fill_id is not None and fill.position_id == pos.position_id
    assert pos.status == "open" and pos.qty_open == 100
    assert pos.opened_on == date(2026, 6, 23)
    assert repo.open_position_for("600519").position_id == pos.position_id


def test_sell_fill_realizes_pnl_and_closes(repo):
    repo.record_fill(OpsFill(code="600519", side="buy", price=10.0, qty=100,
                             filled_at=datetime(2026, 6, 23, 9, 30)))
    fill, pos = repo.record_fill(OpsFill(
        code="600519", side="sell", price=12.0, qty=100,
        filled_at=datetime(2026, 6, 24, 14, 0), fee=3.0))
    assert pos.status == "closed" and pos.qty_open == 0
    assert pos.realized_pnl == pytest.approx((12.0 - 10.0) * 100 - 3.0)
    assert pos.closed_on == date(2026, 6, 24)


def test_fill_marks_linked_decision_executed(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    d = repo.manual_add(s.session_id, "000001", intent_side="buy")
    repo.record_fill(OpsFill(decision_id=d.decision_id, code="000001", side="buy",
                             price=8.0, qty=200, filled_at=datetime(2026, 6, 23, 9, 30)))
    assert repo.decisions_for(s.session_id)[0].status == "executed"


def test_sell_without_position_raises(repo):
    with pytest.raises(ValueError):
        repo.record_fill(OpsFill(code="600519", side="sell", price=12.0, qty=100,
                                 filled_at=datetime(2026, 6, 24, 14, 0)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -k "fill or position" -v`
Expected: FAIL — `AttributeError: 'OpsRepository' object has no attribute 'record_fill'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/ops_repo.py —— import 追加
from youzi.store import account
from youzi.store.models import (
    OpsCandidate, OpsDecision, OpsFill, OpsPosition, OpsSession,
)
```

```python
# youzi/store/ops_repo.py —— OpsRepository 内追加(放在决策方法之后)
    # ── 成交 + 持仓 ──
    def record_fill(self, fill: OpsFill) -> tuple[OpsFill, OpsPosition]:
        pos = self.open_position_for(fill.code)
        if pos is None:
            if fill.side == "sell":
                raise ValueError(f"{fill.code} 无持仓可卖")
            pos = self._create_position(fill)
        state = account.PositionState(
            qty_open=pos.qty_open, avg_cost=pos.avg_cost,
            realized_pnl=pos.realized_pnl, status=pos.status)
        if fill.side == "buy":
            state = account.apply_buy(state, fill.price, fill.qty, fill.fee)
        else:
            state = account.apply_sell(state, fill.price, fill.qty, fill.fee)
        closed_on = fill.filled_at.date() if state.status == "closed" else None
        self._db.execute(
            "UPDATE ops_position SET qty_open=?, avg_cost=?, realized_pnl=?, "
            "status=?, closed_on=? WHERE position_id=?",
            (state.qty_open, state.avg_cost, state.realized_pnl, state.status,
             _iso(closed_on), pos.position_id))
        cur = self._db.execute(
            "INSERT INTO ops_fill (decision_id, position_id, code, side, price, qty, "
            "filled_at, fee, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (fill.decision_id, pos.position_id, fill.code, fill.side, fill.price,
             fill.qty, _iso(fill.filled_at), fill.fee, fill.note))
        if fill.decision_id is not None:
            self._db.execute("UPDATE ops_decision SET status='executed' WHERE decision_id=?",
                             (fill.decision_id,))
        self._db.commit()
        saved_fill = fill.model_copy(update={"fill_id": cur.lastrowid,
                                             "position_id": pos.position_id})
        return saved_fill, self.get_position(pos.position_id)

    def _create_position(self, fill: OpsFill) -> OpsPosition:
        pattern = ""
        if fill.decision_id is not None:
            row = self._db.query_one(
                "SELECT c.pattern AS pattern FROM ops_decision d "
                "LEFT JOIN ops_candidate c ON c.candidate_id=d.candidate_id "
                "WHERE d.decision_id=?", (fill.decision_id,))
            if row and row["pattern"]:
                pattern = row["pattern"]
        cur = self._db.execute(
            "INSERT INTO ops_position (code, pattern, opened_on, status, qty_open, "
            "avg_cost, realized_pnl, origin_decision_id) VALUES (?,?,?,?,?,?,?,?)",
            (fill.code, pattern, _iso(fill.filled_at.date()), "open", 0, 0.0, 0.0,
             fill.decision_id))
        self._db.commit()
        return self.get_position(cur.lastrowid)

    def get_position(self, position_id: int) -> OpsPosition | None:
        row = self._db.query_one(
            "SELECT * FROM ops_position WHERE position_id=?", (position_id,))
        return self._row_to_position(row) if row else None

    def open_position_for(self, code: str) -> OpsPosition | None:
        row = self._db.query_one(
            "SELECT * FROM ops_position WHERE code=? AND status='open' "
            "ORDER BY position_id DESC LIMIT 1", (code,))
        return self._row_to_position(row) if row else None

    def positions(self, status: str | None = None) -> list[OpsPosition]:
        if status is None:
            rows = self._db.query_all(
                "SELECT * FROM ops_position ORDER BY position_id ASC")
        else:
            rows = self._db.query_all(
                "SELECT * FROM ops_position WHERE status=? ORDER BY position_id ASC",
                (status,))
        return [self._row_to_position(r) for r in rows]

    def _row_to_position(self, r) -> OpsPosition:
        return OpsPosition(
            position_id=r["position_id"], code=r["code"], name=r["name"],
            pattern=r["pattern"], opened_on=_parse_date(r["opened_on"]),
            closed_on=_parse_date(r["closed_on"]), status=r["status"],
            qty_open=r["qty_open"], avg_cost=r["avg_cost"],
            realized_pnl=r["realized_pnl"], origin_decision_id=r["origin_decision_id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/ops_repo.py tests/test_ops_repo.py
git commit -m "feat(store): OpsRepository 成交+持仓维护(account 盈亏落库,决策转 executed)"
```

---

## Task 8: OpsRepository — 复盘 + 账户日快照 + 按打法胜率

**Files:**
- Modify: `youzi/store/ops_repo.py`(加复盘/账户/分析 + `_row_to_review`/`_row_to_account`;import 追加 `OpsReview`/`AccountDaily`)
- Test: `tests/test_ops_repo.py`(追加)

**Interfaces:**
- Consumes: Task 5-7 的 `OpsRepository`、`OpsReview`/`AccountDaily`(Task 3)。
- Produces:
  - `add_review(r: OpsReview) -> OpsReview`(回填 id + created_at)
  - `reviews_for_session(session_id) -> list[OpsReview]`
  - `upsert_account_daily(a: AccountDaily) -> AccountDaily`(按 `trade_date` UPSERT)
  - `account_daily(trade_date) -> AccountDaily | None`
  - `pattern_winrate() -> list[dict]`:对**已平仓**持仓按 `pattern` 聚合,返回 `[{"pattern": str, "closed": int, "wins": int, "avg_pnl": float}]`(`wins` = `realized_pnl>0` 计数,`avg_pnl` = 平均 `realized_pnl`),按 `closed` 倒序。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ops_repo.py (追加)
from youzi.store.models import AccountDaily, OpsReview


def test_review_roundtrip(repo):
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    r = repo.add_review(OpsReview(session_id=s.session_id, body="该止盈没止",
                                  tags="情绪误判", lesson_ref="L-退潮-减仓"))
    assert r.review_id is not None and r.created_at == FIXED
    got = repo.reviews_for_session(s.session_id)
    assert got[0].lesson_ref == "L-退潮-减仓"


def test_account_daily_upsert(repo):
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 23), equity=100000.0))
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 23), equity=101000.0))
    a = repo.account_daily(date(2026, 6, 23))
    assert a.equity == pytest.approx(101000.0)        # 覆盖而非重复
    assert a.cash is None                              # 未填诚实 None


def test_pattern_winrate_over_closed_positions(repo):
    # 首板:一盈;连板:一亏。各开平一笔。
    repo.record_fill(OpsFill(code="600519", side="buy", price=10.0, qty=100,
                             filled_at=datetime(2026, 6, 23, 9, 30)))
    # 给 600519 持仓打 pattern(直接建仓无决策 → pattern 空,手动用 review 不影响)。
    # 这里改用带决策的路径验证 pattern 归属:
    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22)))
    [c1] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="000001", rank=1, pattern="连板")])
    d1 = repo.confirm_decision(s.session_id, c1.candidate_id, intent_side="buy")
    repo.record_fill(OpsFill(decision_id=d1.decision_id, code="000001", side="buy",
                             price=20.0, qty=100, filled_at=datetime(2026, 6, 23, 9, 30)))
    repo.record_fill(OpsFill(code="000001", side="sell", price=18.0, qty=100,
                             filled_at=datetime(2026, 6, 24, 14, 0)))
    rows = repo.pattern_winrate()
    lianban = next(r for r in rows if r["pattern"] == "连板")
    assert lianban["closed"] == 1 and lianban["wins"] == 0
    assert lianban["avg_pnl"] == pytest.approx((18.0 - 20.0) * 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -k "review or account or winrate" -v`
Expected: FAIL — `AttributeError: 'OpsRepository' object has no attribute 'add_review'`

- [ ] **Step 3: Write minimal implementation**

```python
# youzi/store/ops_repo.py —— import 追加
from youzi.store.models import (
    AccountDaily, OpsCandidate, OpsDecision, OpsFill,
    OpsPosition, OpsReview, OpsSession,
)
```

```python
# youzi/store/ops_repo.py —— OpsRepository 内追加(放在持仓方法之后)
    # ── 复盘 ──
    def add_review(self, r: OpsReview) -> OpsReview:
        created = r.created_at or self._clock()
        cur = self._db.execute(
            "INSERT INTO ops_review (session_id, position_id, body, tags, lesson_ref, "
            "created_at) VALUES (?,?,?,?,?,?)",
            (r.session_id, r.position_id, r.body, r.tags, r.lesson_ref, _iso(created)))
        self._db.commit()
        return r.model_copy(update={"review_id": cur.lastrowid, "created_at": created})

    def reviews_for_session(self, session_id: int) -> list[OpsReview]:
        rows = self._db.query_all(
            "SELECT * FROM ops_review WHERE session_id=? ORDER BY review_id ASC",
            (session_id,))
        return [self._row_to_review(r) for r in rows]

    def _row_to_review(self, r) -> OpsReview:
        return OpsReview(
            review_id=r["review_id"], session_id=r["session_id"],
            position_id=r["position_id"], body=r["body"], tags=r["tags"],
            lesson_ref=r["lesson_ref"], created_at=_parse_dt(r["created_at"]))

    # ── 账户日快照 ──
    def upsert_account_daily(self, a: AccountDaily) -> AccountDaily:
        self._db.execute(
            "INSERT INTO ops_account_daily (trade_date, equity, cash, market_value, "
            "realized_pnl_day, unrealized_pnl, note) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(trade_date) DO UPDATE SET equity=excluded.equity, "
            "cash=excluded.cash, market_value=excluded.market_value, "
            "realized_pnl_day=excluded.realized_pnl_day, "
            "unrealized_pnl=excluded.unrealized_pnl, note=excluded.note",
            (_iso(a.trade_date), a.equity, a.cash, a.market_value,
             a.realized_pnl_day, a.unrealized_pnl, a.note))
        self._db.commit()
        return a

    def account_daily(self, trade_date: Date) -> AccountDaily | None:
        row = self._db.query_one(
            "SELECT * FROM ops_account_daily WHERE trade_date=?", (_iso(trade_date),))
        if row is None:
            return None
        return AccountDaily(
            trade_date=_parse_date(row["trade_date"]), equity=row["equity"],
            cash=row["cash"], market_value=row["market_value"],
            realized_pnl_day=row["realized_pnl_day"],
            unrealized_pnl=row["unrealized_pnl"], note=row["note"])

    # ── 分析:按打法实战胜率(已平仓)──
    def pattern_winrate(self) -> list[dict]:
        rows = self._db.query_all(
            "SELECT pattern, COUNT(*) AS closed, "
            "SUM(CASE WHEN realized_pnl>0 THEN 1 ELSE 0 END) AS wins, "
            "AVG(realized_pnl) AS avg_pnl FROM ops_position "
            "WHERE status='closed' GROUP BY pattern ORDER BY closed DESC")
        return [{"pattern": r["pattern"], "closed": r["closed"],
                 "wins": r["wins"], "avg_pnl": r["avg_pnl"]} for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add youzi/store/ops_repo.py tests/test_ops_repo.py
git commit -m "feat(store): OpsRepository 复盘+账户日快照+按打法实战胜率"
```

---

## Task 9: 全生命周期集成测试 + 文件库往返

**Files:**
- Modify: `tests/test_ops_repo.py`(追加集成测试)

**Interfaces:**
- Consumes: 全部前序。
- Produces: 无新代码——只验证"会话→候选→决策→分批成交→部分平仓→复盘→账户"端到端,且在**真实文件库**(非 `:memory:`)上跨连接持久化。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ops_repo.py (追加)
def test_full_lifecycle_on_file_db(tmp_path):
    path = tmp_path / "youzi.db"
    db = Database(path)
    db.migrate()
    repo = OpsRepository(db, clock=lambda: FIXED)

    s = repo.create_session(OpsSession(trade_date=date(2026, 6, 22), regime_read="主升"))
    [c] = repo.add_candidates(s.session_id, [
        OpsCandidate(session_id=s.session_id, code="600519", rank=1, pattern="首板",
                     plan_entry=10.0)])
    d = repo.confirm_decision(s.session_id, c.candidate_id, intent_side="buy",
                              planned_price=10.0, planned_qty=200)
    # 分两批买入
    repo.record_fill(OpsFill(decision_id=d.decision_id, code="600519", side="buy",
                             price=10.0, qty=100, filled_at=datetime(2026, 6, 23, 9, 30)))
    _, pos = repo.record_fill(OpsFill(decision_id=d.decision_id, code="600519", side="buy",
                                      price=12.0, qty=100,
                                      filled_at=datetime(2026, 6, 23, 13, 0)))
    assert pos.qty_open == 200 and pos.avg_cost == pytest.approx(11.0)
    # 部分平仓
    _, pos = repo.record_fill(OpsFill(code="600519", side="sell", price=13.0, qty=100,
                                      filled_at=datetime(2026, 6, 24, 14, 0)))
    assert pos.qty_open == 100 and pos.status == "open"
    assert pos.realized_pnl == pytest.approx((13.0 - 11.0) * 100)
    repo.add_review(OpsReview(session_id=s.session_id, position_id=pos.position_id,
                              body="减半仓", tags="主升兑现"))
    repo.upsert_account_daily(AccountDaily(trade_date=date(2026, 6, 24),
                                           realized_pnl_day=200.0))
    db.close()

    # 跨连接重开,数据仍在
    db2 = Database(path)
    repo2 = OpsRepository(db2)
    assert repo2.get_session(s.session_id).regime_read == "主升"
    assert repo2.open_position_for("600519").qty_open == 100
    assert repo2.account_daily(date(2026, 6, 24)).realized_pnl_day == pytest.approx(200.0)
    db2.close()
```

- [ ] **Step 2: Run test to verify it fails (or passes immediately)**

Run: `.venv/bin/python -m pytest tests/test_ops_repo.py::test_full_lifecycle_on_file_db -v`
Expected: PASS(若全 Task 实现正确,集成测试应直接通过)。如失败,定位到具体环节修复对应 Task。

- [ ] **Step 3: 无新增实现**(集成测试覆盖既有代码)

- [ ] **Step 4: Run the whole suite to confirm 全绿 + 离线**

Run: `.venv/bin/python -m pytest`
Expected: 全部通过(原 466 + 本期新增),无触网。

- [ ] **Step 5: Commit**

```bash
git add tests/test_ops_repo.py
git commit -m "test(store): 运营全闭环端到端集成 + 文件库跨连接持久化"
```

---

## 收尾验证

- [ ] **全量测试**:`.venv/bin/python -m pytest` → 全绿。
- [ ] **离线确认**:本期无任何 akshare/DeepSeek import 进 `youzi/store/`;`grep -rn "akshare\|deepseek\|requests\|httpx" youzi/store/` 应为空。
- [ ] **分层确认**:`youzi/store/` 不 import `youzi_web`;决策路径(`youzi/agent/`)不 import `youzi/store/`(本期未碰,grep 确认零引用)。
- [ ] 更新 `PROJECT_STATE.md` + memory:store 地基 + 运营全闭环领域层入分支,待 FF。

## 下一份计划(B-web,本计划之外)

`OpsRepository` 之上的 web 层:`youzi_web/features/ops/`(`registry.Feature` append)——录入决策/回填成交/复盘/权益曲线页面 + 经领域命令 API 的 FastAPI 路由(守"web 经命令 API 读+写、不触领域内部")。落地本计划、验证全绿后,回到 brainstorm→spec→plan 循环单独成计划。
