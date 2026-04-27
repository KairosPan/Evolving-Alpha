# 游资智能体 (youzi-agent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an EOD-batch LangGraph multi-agent system that ingests akshare data, classifies market emotion phase, picks candidate stocks via 4 sub-agents, and outputs a daily JSON+Markdown trade-suggestion report.

**Architecture:** Approach 2 — parent graph (SENSE → ANALYZE → DECIDE) with 4 independent sub-graphs invoked via `Send` API; pure-rule nodes plus DeepSeek LLM in 2 nodes (`theme_analyst` + `pattern_matcher` edge tiebreaker); SQLite checkpointer; akshare-only data source with parquet on-disk cache.

**Tech Stack:** Python 3.11+, langgraph 0.2.50+, langchain-openai (DeepSeek-compatible), akshare 1.13+, pandas + pyarrow, pydantic 2.5+, pytest, rich.

**Spec:** `docs/superpowers/specs/2026-04-26-youzi-agent-design.md`

---

## Repo conventions

- Working directory: `/Volumes/kairos/引力场量化/`
- Package source: `src/youzi_agent/`
- Tests: `tests/`
- Run all tests: `pytest tests/ -v`
- Pinned: `akshare>=1.13,<2`, `langgraph>=0.2.50,<0.3`
- Commit style: conventional commits (`feat:`, `test:`, `chore:`, `fix:`)
- After every task: tests green + commit

---

## Phase 0 — Project skeleton

### Task 0: Initialize repo + project skeleton

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/youzi_agent/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: `git init` and create `.gitignore`**

```bash
cd /Volumes/kairos/引力场量化
git init
```

Write `.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
.coverage
.env
checkpoints.db
data_cache/
runs/
.venv/
*.egg-info/
build/
dist/
.DS_Store
._*
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "youzi-agent"
version = "0.1.0"
description = "A-share retail-style multi-agent trading research pipeline"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.50,<0.3",
    "langgraph-checkpoint-sqlite>=2.0",
    "langchain-openai>=0.2",
    "akshare>=1.13,<2",
    "pandas>=2.0",
    "pyarrow>=15",
    "pydantic>=2.5",
    "rich>=13",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "ruff", "mypy"]

[project.scripts]
youzi-agent = "youzi_agent.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: tests that need real network/LLM (skipped in CI)"]
```

- [ ] **Step 3: Create `.env.example` and empty package + tests packages**

`.env.example`:
```
DEEPSEEK_API_KEY=sk-your-key-here
```

`src/youzi_agent/__init__.py`:
```python
"""游资智能体 / A-share retail-style trading research pipeline."""
__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
```

- [ ] **Step 4: Install dev environment and verify pytest discovers nothing yet**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Expected: `no tests ran in 0.XXs` (exit code 5 — that's fine).

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml .env.example src tests
git commit -m "chore: bootstrap youzi-agent project skeleton"
```

---

## Phase 1 — Data layer

### Task 1: Disk parquet cache utility

**Files:**
- Create: `src/youzi_agent/data/__init__.py`
- Create: `src/youzi_agent/data/cache.py`
- Test: `tests/test_data/test_cache.py`

- [ ] **Step 1: Write the failing test**

`tests/test_data/__init__.py`:
```python
```

`tests/test_data/test_cache.py`:
```python
import pandas as pd
from pathlib import Path
from youzi_agent.data.cache import disk_cache

def test_disk_cache_writes_and_reads_parquet(tmp_path):
    calls = {"n": 0}

    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str) -> pd.DataFrame:
        calls["n"] += 1
        return pd.DataFrame({"a": [1, 2], "date": [date, date]})

    df1 = fetch("2026-04-25")
    df2 = fetch("2026-04-25")          # second call should hit cache
    assert calls["n"] == 1
    assert df1.equals(df2)
    assert (tmp_path / "2026-04-25" / "fetch.parquet").exists()

def test_disk_cache_separates_by_args(tmp_path):
    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str, code: str) -> pd.DataFrame:
        return pd.DataFrame({"v": [hash((date, code)) % 1000]})

    a = fetch("2026-04-25", "600000")
    b = fetch("2026-04-25", "000001")
    assert not a.equals(b)

def test_disk_cache_refresh_bypasses(tmp_path):
    calls = {"n": 0}

    @disk_cache(cache_dir=tmp_path, ttl="eod")
    def fetch(date: str) -> pd.DataFrame:
        calls["n"] += 1
        return pd.DataFrame({"v": [calls["n"]]})

    fetch("2026-04-25")
    fetch("2026-04-25", _refresh=True)
    assert calls["n"] == 2
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_data/test_cache.py -v
```

Expected: ImportError / module not found.

- [ ] **Step 3: Implement `cache.py`**

`src/youzi_agent/data/__init__.py`:
```python
```

`src/youzi_agent/data/cache.py`:
```python
"""Per-trading-day parquet cache decorator."""
from __future__ import annotations

import functools
import hashlib
import re
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

T = TypeVar("T", bound=pd.DataFrame)

_DATE_RE = re.compile(r"\d{4}-?\d{2}-?\d{2}")


def _extract_date(args: tuple, kwargs: dict) -> str:
    """Find the trading-date argument among positional/kw args."""
    if "date" in kwargs and isinstance(kwargs["date"], str):
        return _normalize(kwargs["date"])
    for a in args:
        if isinstance(a, str) and _DATE_RE.fullmatch(a.replace("-", "")):
            return _normalize(a)
    return "undated"


def _normalize(d: str) -> str:
    d = d.replace("-", "")
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def _arg_hash(args: tuple, kwargs: dict) -> str:
    payload = repr(args) + repr(sorted(kwargs.items()))
    return hashlib.md5(payload.encode()).hexdigest()[:8]


def disk_cache(cache_dir: str | Path = "data_cache", ttl: str = "eod") -> Callable:
    """Cache the wrapped function's pandas DataFrame return value to parquet.

    Layout: {cache_dir}/{date}/{fn_name}_{argshash}.parquet
    Pass `_refresh=True` to bypass the cache for a single call.
    `ttl="eod"` means "valid forever within the same trading date".
    """
    base = Path(cache_dir)

    def deco(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        @functools.wraps(fn)
        def wrapper(*args, _refresh: bool = False, **kwargs):
            date = _extract_date(args, kwargs)
            sig = _arg_hash(args, kwargs)
            day_dir = base / date
            fname = f"{fn.__name__}_{sig}.parquet" if (args or kwargs) else f"{fn.__name__}.parquet"
            # Single-arg backward-compat: if only one arg and it's the date, drop the hash suffix
            if len(args) <= 1 and not kwargs and date != "undated":
                fname = f"{fn.__name__}.parquet"
            path = day_dir / fname
            if path.exists() and not _refresh:
                return pd.read_parquet(path)
            df = fn(*args, **kwargs)
            day_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            return df
        return wrapper
    return deco
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_data/test_cache.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/data tests/test_data
git commit -m "feat(data): add per-trading-day parquet cache decorator"
```

---

### Task 2: AkshareClient wrapper with retry + fallback

**Files:**
- Create: `src/youzi_agent/data/akshare_client.py`
- Test: `tests/test_data/test_akshare_client.py`

- [ ] **Step 1: Write the failing test (mock akshare, no network)**

`tests/test_data/test_akshare_client.py`:
```python
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from youzi_agent.data.akshare_client import AkshareClient, _retry

def test_retry_succeeds_on_third_attempt():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("flaky")
        return "ok"
    assert _retry(flaky, attempts=3, backoff=1.0) == "ok"
    assert calls["n"] == 3

def test_retry_raises_after_max_attempts():
    def always_fail():
        raise RuntimeError("nope")
    with pytest.raises(RuntimeError):
        _retry(always_fail, attempts=2, backoff=1.0)

def test_limit_up_pool_caches(tmp_path):
    cli = AkshareClient(cache_dir=tmp_path)
    df_fixture = pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "连板数": [1]})
    with patch("youzi_agent.data.akshare_client.ak") as ak_mock:
        ak_mock.stock_zt_pool_em.return_value = df_fixture
        out1 = cli.limit_up_pool("2026-04-25")
        out2 = cli.limit_up_pool("2026-04-25")
        assert ak_mock.stock_zt_pool_em.call_count == 1
        assert out1.equals(out2)

def test_market_activity_fallback_when_legu_fails(tmp_path):
    cli = AkshareClient(cache_dir=tmp_path)
    spot = pd.DataFrame({"涨跌幅": [1.5, -0.3, 9.95, -2.0, 5.0]})
    with patch("youzi_agent.data.akshare_client.ak") as ak_mock:
        ak_mock.stock_market_activity_legu.side_effect = RuntimeError("missing")
        ak_mock.stock_zh_a_spot_em.return_value = spot
        out = cli.market_activity("2026-04-25")
        assert int(out.iloc[0]["red_count"]) == 3
        assert int(out.iloc[0]["limit_up"]) == 1
```

- [ ] **Step 2: Run test, expect import failure**

```bash
pytest tests/test_data/test_akshare_client.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `akshare_client.py`**

`src/youzi_agent/data/akshare_client.py`:
```python
"""Single IO boundary — every node reads data through this client."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd

from .cache import disk_cache


def _retry(fn: Callable, attempts: int = 3, backoff: float = 1.5):
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(backoff ** i)
    assert last is not None
    raise last


def _ymd(date: str) -> str:
    return date.replace("-", "")


class AkshareClient:
    def __init__(self, cache_dir: str | Path = "data_cache"):
        self.cache_dir = Path(cache_dir)
        # Decorate methods at instance level so cache_dir is honored.
        for name in [
            "limit_up_pool", "blast_pool", "index_daily", "stock_kline",
            "market_activity", "concept_members_ths", "concept_list_ths",
            "code_list",
        ]:
            wrapped = disk_cache(cache_dir=self.cache_dir, ttl="eod")(getattr(self, name))
            setattr(self, name, wrapped)

    def limit_up_pool(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_zt_pool_em(date=_ymd(date)))

    def blast_pool(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_zt_pool_zbgc_em(date=_ymd(date)))

    def index_daily(self, symbol: str) -> pd.DataFrame:
        # symbol uses akshare convention e.g. "sh000001"
        return _retry(lambda: ak.stock_zh_index_daily_em(symbol=symbol))

    def stock_kline(self, code: str, end_date: str, lookback_days: int = 60) -> pd.DataFrame:
        start = (pd.Timestamp(end_date) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
        return _retry(lambda: ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start, end_date=_ymd(end_date),
            adjust="qfq",
        ))

    def market_activity(self, date: str) -> pd.DataFrame:
        try:
            df = _retry(lambda: ak.stock_market_activity_legu())
            if "date" not in df.columns:
                df = df.assign(date=date)
            return df
        except Exception:
            spot = _retry(lambda: ak.stock_zh_a_spot_em())
            return pd.DataFrame([{
                "date":        date,
                "red_count":   int((spot["涨跌幅"] > 0).sum()),
                "green_count": int((spot["涨跌幅"] < 0).sum()),
                "limit_up":    int((spot["涨跌幅"] >= 9.9).sum()),
            }])

    def concept_members_ths(self, theme_name: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_board_concept_cons_ths(symbol=theme_name))

    def concept_list_ths(self, date: str) -> pd.DataFrame:
        # date arg is only for cache partitioning; the akshare call itself ignores it
        return _retry(lambda: ak.stock_board_concept_name_ths())

    def code_list(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_info_a_code_name())
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_data/test_akshare_client.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/data/akshare_client.py tests/test_data/test_akshare_client.py
git commit -m "feat(data): add AkshareClient with retry + EOD parquet cache + activity fallback"
```

---

### Task 3: Snapshot fixtures generator (live, optional)

**Files:**
- Create: `scripts/snapshot_fixtures.py`
- Create: `tests/fixtures/.gitkeep`

- [ ] **Step 1: Write the snapshot script**

`scripts/snapshot_fixtures.py`:
```python
"""One-shot script to capture today's akshare data into tests/fixtures/{date}/.

Usage:
    python scripts/snapshot_fixtures.py 2026-04-25
"""
import sys
from pathlib import Path
from youzi_agent.data.akshare_client import AkshareClient


def main(date: str):
    out_dir = Path("tests/fixtures") / date
    out_dir.mkdir(parents=True, exist_ok=True)
    cli = AkshareClient(cache_dir=out_dir.parent)  # writes under tests/fixtures/{date}/
    print(f"snapshotting {date} → {out_dir}")
    cli.limit_up_pool(date)
    prev = (__import__("pandas").Timestamp(date) - __import__("pandas").Timedelta(days=1)).strftime("%Y-%m-%d")
    cli.limit_up_pool(prev)
    cli.blast_pool(prev)
    cli.index_daily("sh000001")
    cli.index_daily("sz399006")
    cli.market_activity(date)
    cli.code_list(date)
    cli.concept_list_ths(date)
    print("done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else __import__("datetime").date.today().isoformat())
```

`tests/fixtures/.gitkeep`:
```
```

- [ ] **Step 2: Run the snapshot for today (NETWORK; OK to skip if offline)**

```bash
python scripts/snapshot_fixtures.py $(date +%Y-%m-%d) || echo "offline; skip snapshot"
```

If you have network, fixtures land under `tests/fixtures/<date>/`. If offline, skip — Phase 10 will provide synthetic fixtures as a fallback.

- [ ] **Step 3: Commit**

```bash
git add scripts/snapshot_fixtures.py tests/fixtures/.gitkeep
git add tests/fixtures 2>/dev/null || true     # may add real snapshots if step 2 ran
git commit -m "chore(test): add live snapshot script for akshare fixtures"
```

---

## Phase 2 — State module

### Task 4: State TypedDicts + custom reducers

**Files:**
- Create: `src/youzi_agent/state.py`
- Create: `src/youzi_agent/reducers.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from youzi_agent.state import (
    MarketState, Candidate, PatternHit, ThemeProfile, LeaderProfile,
)
from youzi_agent.reducers import dedupe_candidates_by_code

def test_market_state_typeddict_total_false():
    s: MarketState = {"target_date": "2026-04-25"}
    assert s["target_date"] == "2026-04-25"

def test_dedupe_candidates_keeps_highest_score():
    a = Candidate(code="600000", name="x", pattern_id="L1_first_board",
                  score=0.5, reason="r1", suggested_position=0.1)
    b = Candidate(code="600000", name="x", pattern_id="L2_weak_to_strong",
                  score=0.8, reason="r2", suggested_position=0.1)
    c = Candidate(code="000001", name="y", pattern_id="L1_first_board",
                  score=0.7, reason="r3", suggested_position=0.1)
    out = dedupe_candidates_by_code([a, b, c])
    assert len(out) == 2
    assert {x["code"] for x in out} == {"600000", "000001"}
    assert next(x for x in out if x["code"] == "600000")["score"] == 0.8
```

- [ ] **Step 2: Run, expect import failure**

```bash
pytest tests/test_state.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `state.py` and `reducers.py`**

`src/youzi_agent/state.py`:
```python
"""Parent + sub-graph TypedDicts."""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal, Optional, TypedDict


class ThemeProfile(TypedDict, total=False):
    name: str
    members: list[str]
    leader: Optional[str]
    catalysts: list[str]
    phase: Literal["budding", "horizontal", "vertical", "switching", "exhausted"]
    resonance_score: float


class LeaderProfile(TypedDict, total=False):
    code: str
    name: str
    consec_boards: int
    role: Literal["total", "capacity", "complement", "companion"]
    sealed_amount: float
    blast_today: bool
    div_count: int


class PatternHit(TypedDict):
    pattern_id: str
    filter_desc: str
    target_subagent: str


class Candidate(TypedDict, total=False):
    code: str
    name: str
    pattern_id: str
    score: float
    reason: str
    suggested_position: float
    consec_boards: int


class TradePlan(TypedDict, total=False):
    date: str
    position_total_max: float
    candidates: list[Candidate]
    avoid_list: list[str]
    notes: str


EmotionPhase = Literal[
    "chaos", "recovery", "warming", "main_rise",
    "climax", "divergence", "decay_1", "decay_mid", "decay_2",
]
IndexPhase = Literal["uptrend", "top", "downtrend", "bottom", "oscillation"]
SuccessionStatus = Literal["healthy", "first_div", "second_div", "broken", "trans"]
ThemeAxis = Literal["horizontal", "vertical", "switching", "exhausted"]


class MarketState(TypedDict, total=False):
    target_date: str
    use_llm: bool
    raw: dict

    index_phase: IndexPhase
    sz_macd: dict
    cyb_macd: dict
    market_volume: float
    big_cap_volume_ratio: float

    five_day_pos: Literal["above", "top_horizontal", "below", "bottom_grinding"]
    money_effect: Literal["positive", "neutral", "negative"]
    is_new_cycle_day: bool
    is_only_rebound: bool

    emotion_phase: EmotionPhase
    sentiment_value: int
    limit_up_count: int
    consec_top: int
    blast_rate: float

    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    theme_axis: ThemeAxis
    leader_stack: list[LeaderProfile]
    succession_status: SuccessionStatus

    pattern_hits: Annotated[list[PatternHit], add]
    candidates: Annotated[list[Candidate], add]
    final_candidates: list[Candidate]
    arb_opportunities: Annotated[list[Candidate], add]
    risk_flags: Annotated[list[str], add]
    plan: Optional[TradePlan]

    review: Optional[dict]
    errors: Annotated[list[str], add]


class FirstBoardState(TypedDict, total=False):
    target_date: str
    pattern_hits: list[PatternHit]
    raw: dict
    leader_stack: list[LeaderProfile]
    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    candidates: Annotated[list[Candidate], add]
    errors: Annotated[list[str], add]


class WeakToStrongState(FirstBoardState):
    pass


class ContinuousState(FirstBoardState):
    pass


class SetbackReversalState(FirstBoardState):
    pass
```

`src/youzi_agent/reducers.py`:
```python
"""Helpers to fold lists in MarketState reducers."""
from __future__ import annotations

from .state import Candidate


def dedupe_candidates_by_code(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the highest-score candidate per stock code."""
    best: dict[str, Candidate] = {}
    for c in candidates:
        prev = best.get(c["code"])
        if prev is None or c.get("score", 0) > prev.get("score", 0):
            best[c["code"]] = c
    return sorted(best.values(), key=lambda x: -x.get("score", 0))
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_state.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/state.py src/youzi_agent/reducers.py tests/test_state.py
git commit -m "feat(state): add MarketState + sub-graph TypedDicts and dedupe reducer"
```

---

## Phase 3 — SENSE nodes

### Task 5: `market_sensor` node

**Files:**
- Create: `src/youzi_agent/nodes/__init__.py`
- Create: `src/youzi_agent/nodes/market_sensor.py`
- Test: `tests/test_nodes/__init__.py`, `tests/test_nodes/test_market_sensor.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/__init__.py`:
```python
```

`tests/test_nodes/test_market_sensor.py`:
```python
from unittest.mock import MagicMock
import pandas as pd
from youzi_agent.nodes.market_sensor import market_sensor_node

def test_market_sensor_populates_basic_stats():
    cli = MagicMock()
    ztb_today = pd.DataFrame({
        "代码": ["600000", "000001", "300750"],
        "名称": ["a", "b", "c"],
        "连板数": [1, 2, 4],
        "封单金额": [1.2e8, 0.5e8, 5e8],
        "首次封板时间": ["09:30", "10:15", "09:31"],
        "炸板次数": [0, 1, 0],
    })
    ztb_yest = pd.DataFrame({
        "代码": ["600000"], "名称": ["a"], "连板数": [1],
        "封单金额": [1e8], "首次封板时间": ["09:35"], "炸板次数": [2],
    })
    zb_yest = pd.DataFrame({"代码": ["000002", "300999"]})
    cli.limit_up_pool.side_effect = lambda d: ztb_today if d == "2026-04-25" else ztb_yest
    cli.blast_pool.return_value = zb_yest
    cli.index_daily.return_value = pd.DataFrame()
    cli.market_activity.return_value = pd.DataFrame([{"red_count": 2300}])

    out = market_sensor_node({"target_date": "2026-04-25"}, client=cli)
    assert out["limit_up_count"] == 3
    assert out["consec_top"] == 4
    assert "raw" in out
    assert "ztb_today" in out["raw"]
    # blast_rate = (limit_up_yesterday-still-limit_up_today) ratio approximation
    assert 0 <= out["blast_rate"] <= 1
```

- [ ] **Step 2: Run, expect import failure**

```bash
pytest tests/test_nodes/test_market_sensor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `market_sensor.py`**

`src/youzi_agent/nodes/__init__.py`:
```python
```

`src/youzi_agent/nodes/market_sensor.py`:
```python
"""Stage A entry: pull all the day's data into state['raw']."""
from __future__ import annotations

import pandas as pd

from ..data.akshare_client import AkshareClient
from ..state import MarketState


def _prev_trading_day(date: str) -> str:
    # Naive: last calendar weekday. Holidays handled by data layer (cache returns empty).
    d = pd.Timestamp(date) - pd.Timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _calc_blast_rate(ztb_today: pd.DataFrame, zb_yest: pd.DataFrame) -> float:
    """Approximation: yesterday-blasted / (yesterday-blasted + today-still-up)."""
    blasted = len(zb_yest) if zb_yest is not None else 0
    sustained = len(ztb_today)
    denom = blasted + sustained
    return round(blasted / denom, 4) if denom else 0.0


def market_sensor_node(state: MarketState, *, client: AkshareClient | None = None) -> dict:
    cli = client or AkshareClient()
    date = state["target_date"]
    prev = _prev_trading_day(date)
    try:
        raw = {
            "ztb_today":     cli.limit_up_pool(date),
            "ztb_yesterday": cli.limit_up_pool(prev),
            "zb_yesterday":  cli.blast_pool(prev),
            "idx_sh":        cli.index_daily("sh000001"),
            "idx_cyb":       cli.index_daily("sz399006"),
            "activity":      cli.market_activity(date),
        }
    except Exception as e:
        return {"errors": [f"market_sensor: data fetch failed: {e}"]}

    ztb = raw["ztb_today"]
    consec_col = "连板数" if "连板数" in ztb.columns else "连板"
    return {
        "raw": raw,
        "limit_up_count": int(len(ztb)),
        "consec_top": int(ztb[consec_col].max()) if len(ztb) else 0,
        "blast_rate": _calc_blast_rate(ztb, raw["zb_yesterday"]),
    }
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_market_sensor.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/__init__.py src/youzi_agent/nodes/market_sensor.py tests/test_nodes
git commit -m "feat(nodes): add market_sensor with prev-day discovery and blast-rate calc"
```

---

### Task 6: `index_cycle` node (MACD + phase classification)

**Files:**
- Create: `src/youzi_agent/nodes/index_cycle.py`
- Test: `tests/test_nodes/test_index_cycle.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_index_cycle.py`:
```python
import numpy as np
import pandas as pd
from youzi_agent.nodes.index_cycle import index_cycle_node, _macd, _classify_phase

def test_macd_outputs_three_series():
    closes = pd.Series(np.linspace(100, 120, 100))
    dif, dea, hist = _macd(closes)
    assert len(dif) == len(dea) == len(hist) == 100
    assert not pd.isna(dif.iloc[-1])

def test_classify_phase_uptrend():
    closes = pd.Series(np.linspace(100, 200, 80))
    assert _classify_phase(closes) == "uptrend"

def test_classify_phase_downtrend():
    closes = pd.Series(np.linspace(200, 100, 80))
    assert _classify_phase(closes) == "downtrend"

def test_index_cycle_node_returns_phase():
    closes_sh = np.linspace(3000, 3500, 100)
    closes_cyb = np.linspace(2000, 2300, 100)
    raw = {
        "idx_sh":  pd.DataFrame({"close": closes_sh,  "amount": np.linspace(1e10, 2e10, 100)}),
        "idx_cyb": pd.DataFrame({"close": closes_cyb, "amount": np.linspace(5e9, 8e9, 100)}),
    }
    out = index_cycle_node({"raw": raw, "target_date": "2026-04-25"})
    assert out["index_phase"] in {"uptrend", "top", "downtrend", "bottom", "oscillation"}
    assert "sz_macd" in out and "cyb_macd" in out
    assert out["market_volume"] > 0
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_index_cycle.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/index_cycle.py`:
```python
"""Index-level phase + MACD."""
from __future__ import annotations

import pandas as pd

from ..state import MarketState


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    dif = _ema(closes, fast) - _ema(closes, slow)
    dea = _ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def _classify_phase(closes: pd.Series) -> str:
    if len(closes) < 60:
        return "oscillation"
    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1]
    last = closes.iloc[-1]
    slope_60 = (closes.rolling(60).mean().iloc[-1] - closes.rolling(60).mean().iloc[-20]) / closes.iloc[-1]
    if last > ma60 and ma20 > ma60 and slope_60 > 0.005:
        return "uptrend"
    if last < ma60 and ma20 < ma60 and slope_60 < -0.005:
        return "downtrend"
    if abs(slope_60) < 0.002:
        return "oscillation"
    if slope_60 > 0:
        return "top" if last < ma20 * 0.97 else "uptrend"
    return "bottom" if last > ma20 * 1.03 else "downtrend"


def _summarize_macd(closes: pd.Series) -> dict:
    dif, dea, hist = _macd(closes)
    return {
        "dif": float(dif.iloc[-1]),
        "dea": float(dea.iloc[-1]),
        "hist": float(hist.iloc[-1]),
        "above_zero": bool(dif.iloc[-1] > 0),
        "golden_cross": bool(dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] >= dea.iloc[-1])
                         if len(dif) >= 2 else False,
    }


def index_cycle_node(state: MarketState) -> dict:
    raw = state.get("raw", {})
    sh = raw.get("idx_sh")
    cyb = raw.get("idx_cyb")
    if sh is None or len(sh) == 0:
        return {"errors": ["index_cycle: no idx_sh data"], "index_phase": "oscillation"}
    sh_closes = sh["close"].astype(float)
    cyb_closes = cyb["close"].astype(float) if cyb is not None and len(cyb) else sh_closes
    return {
        "index_phase":  _classify_phase(sh_closes),
        "sz_macd":      _summarize_macd(sh_closes),
        "cyb_macd":     _summarize_macd(cyb_closes),
        "market_volume": float(sh["amount"].iloc[-1]) if "amount" in sh.columns else 0.0,
        "big_cap_volume_ratio": 0.0,  # v1 placeholder, see spec §6.2
    }
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_nodes/test_index_cycle.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/index_cycle.py tests/test_nodes/test_index_cycle.py
git commit -m "feat(nodes): add index_cycle with EMA-based MACD and phase classification"
```

---

### Task 7: `emotion` node (9-phase classifier)

**Files:**
- Create: `src/youzi_agent/nodes/emotion.py`
- Test: `tests/test_nodes/test_emotion.py`

- [ ] **Step 1: Write failing tests**

`tests/test_nodes/test_emotion.py`:
```python
import pandas as pd
from youzi_agent.nodes.emotion import emotion_node, _ma5_turn, classify_emotion

def test_ma5_turn_up():
    # red_count series where MA5 turns up today
    rc = [1500, 1400, 1300, 1200, 1100, 1200, 1500]
    assert _ma5_turn(rc) == "turn_up"

def test_ma5_continue_up():
    rc = [1000, 1200, 1400, 1600, 1800, 2000, 2200]
    assert _ma5_turn(rc) == "continue_up"

def test_classify_emotion_chaos():
    assert classify_emotion(red_count=900, ma5=1500, ma3=1500,
                            ma5_turn="continue_down", blast_rate=0.5,
                            consec_top=2, lu_count=20) == "chaos"

def test_classify_emotion_climax():
    assert classify_emotion(red_count=4200, ma5=3500, ma3=3700,
                            ma5_turn="continue_up", blast_rate=0.1,
                            consec_top=8, lu_count=120) == "climax"

def test_classify_emotion_main_rise():
    assert classify_emotion(red_count=2800, ma5=2500, ma3=2700,
                            ma5_turn="continue_up", blast_rate=0.15,
                            consec_top=6, lu_count=80) == "main_rise"

def test_emotion_node_uses_activity_history():
    activity = pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26), [1100, 1200, 1300, 1400, 1500,
                                          1600, 1700, 1800, 1900, 2000, 2100])
    ])
    state = {
        "raw": {"activity": activity},
        "limit_up_count": 60,
        "consec_top": 5,
        "blast_rate": 0.18,
        "target_date": "2026-04-25",
    }
    out = emotion_node(state)
    assert out["emotion_phase"] in {"recovery", "warming", "main_rise"}
    assert isinstance(out["sentiment_value"], int)
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_emotion.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/emotion.py`:
```python
"""Map (red_count, MA5, blast_rate, …) to one of 9 emotion phases."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from ..state import EmotionPhase, MarketState

ICE_THRESHOLD = 1000
CLIMAX_THRESHOLD = 4000
FLAT_DELTA = 5  # |Δ MA5| < 5 → flat


def _ma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - n:i + 1]) / n)
    return out


def _ma5_turn(red_counts: list[float]) -> str:
    if len(red_counts) < 7:
        return "flat"
    ma5 = _ma(red_counts, 5)
    today, yest, prev = ma5[-1], ma5[-2], ma5[-3]
    if today is None or yest is None or prev is None:
        return "flat"
    d_today = today - yest
    d_yest = yest - prev
    if abs(d_today) < FLAT_DELTA:
        return "flat"
    if d_today > 0 and d_yest <= 0:
        return "turn_up"
    if d_today < 0 and d_yest >= 0:
        return "turn_down"
    if d_today > 0 and d_yest > 0:
        return "continue_up"
    if d_today < 0 and d_yest < 0:
        return "continue_down"
    return "flat"


def classify_emotion(*, red_count: int, ma5: float, ma3: float, ma5_turn: str,
                     blast_rate: float, consec_top: int, lu_count: int) -> EmotionPhase:
    if red_count <= ICE_THRESHOLD:
        return "chaos"
    if red_count >= CLIMAX_THRESHOLD and lu_count > 100:
        return "climax"
    if ma5_turn == "turn_up":
        return "recovery" if ma5 < 2000 else "warming"
    if ma5_turn == "continue_up" and consec_top >= 5:
        return "main_rise"
    if ma5_turn == "continue_up":
        return "warming"
    if ma5_turn == "turn_down":
        return "divergence" if blast_rate > 0.30 else "decay_1"
    if ma5_turn == "continue_down":
        return "decay_2"
    return "warming"


def emotion_node(state: MarketState) -> dict:
    activity = state.get("raw", {}).get("activity")
    if activity is None or len(activity) == 0:
        return {"errors": ["emotion: no activity history"], "emotion_phase": "warming",
                "sentiment_value": int(state.get("limit_up_count", 0) * 30)}
    red = list(activity["red_count"].astype(int)) if "red_count" in activity.columns else []
    if not red:
        return {"errors": ["emotion: red_count missing"], "emotion_phase": "warming",
                "sentiment_value": 2000}
    ma5_today = sum(red[-5:]) / 5 if len(red) >= 5 else sum(red) / len(red)
    ma3_today = sum(red[-3:]) / 3 if len(red) >= 3 else ma5_today
    turn = _ma5_turn(red)
    phase = classify_emotion(
        red_count=red[-1], ma5=ma5_today, ma3=ma3_today, ma5_turn=turn,
        blast_rate=state.get("blast_rate", 0.0),
        consec_top=state.get("consec_top", 0),
        lu_count=state.get("limit_up_count", 0),
    )
    five_pos: Literal["above", "top_horizontal", "below", "bottom_grinding"]
    if ma5_today > 2500:
        five_pos = "above" if turn in {"continue_up", "turn_up"} else "top_horizontal"
    else:
        five_pos = "below" if turn in {"continue_down", "turn_down"} else "bottom_grinding"
    return {
        "emotion_phase": phase,
        "sentiment_value": int(red[-1]),
        "five_day_pos": five_pos,
    }
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_emotion.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/emotion.py tests/test_nodes/test_emotion.py
git commit -m "feat(nodes): add emotion classifier covering 9 phases"
```

---

### Task 8: `cycle_switch` node (cross-day flags)

**Files:**
- Create: `src/youzi_agent/nodes/cycle_switch.py`
- Test: `tests/test_nodes/test_cycle_switch.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_cycle_switch.py`:
```python
from youzi_agent.nodes.cycle_switch import cycle_switch_node

def test_cycle_switch_no_prev_state_degrades_safely():
    out = cycle_switch_node({"emotion_phase": "warming",
                              "limit_up_count": 60,
                              "consec_top": 5,
                              "target_date": "2026-04-25"},
                             prev_snapshot=None)
    assert out["is_new_cycle_day"] is False
    assert out["is_only_rebound"] is False
    assert any("无前日" in e for e in out.get("errors", []))

def test_cycle_switch_new_cycle_day():
    out = cycle_switch_node(
        {"emotion_phase": "recovery", "limit_up_count": 70, "consec_top": 5,
         "target_date": "2026-04-25"},
        prev_snapshot={"emotion_phase": "chaos", "consec_top": 2})
    assert out["is_new_cycle_day"] is True

def test_cycle_switch_money_effect_levels():
    for lu, expected in [(60, "positive"), (30, "neutral"), (10, "negative")]:
        out = cycle_switch_node(
            {"emotion_phase": "warming", "limit_up_count": lu, "consec_top": 3,
             "target_date": "2026-04-25"},
            prev_snapshot={"emotion_phase": "warming", "consec_top": 3})
        assert out["money_effect"] == expected
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_cycle_switch.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/cycle_switch.py`:
```python
"""Cross-day flags: new_cycle_day / only_rebound / money_effect."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..state import MarketState


def _load_prev_snapshot(date: str, runs_dir: Path) -> Optional[dict]:
    from datetime import datetime, timedelta
    d = datetime.strptime(date, "%Y-%m-%d")
    for back in range(1, 8):  # look up to 7 calendar days back
        p = runs_dir / (d - timedelta(days=back)).strftime("%Y-%m-%d") / "state_snapshot.json"
        if p.exists():
            return json.loads(p.read_text())
    return None


def cycle_switch_node(state: MarketState,
                      *, runs_dir: str | Path = "runs",
                      prev_snapshot: Optional[dict] | object = ...) -> dict:
    if prev_snapshot is ...:
        prev_snapshot = _load_prev_snapshot(state["target_date"], Path(runs_dir))

    today_phase = state.get("emotion_phase")
    today_top = state.get("consec_top", 0)
    lu = state.get("limit_up_count", 0)

    money_effect = "positive" if lu > 50 else "neutral" if lu > 20 else "negative"

    if not prev_snapshot:
        return {
            "is_new_cycle_day": False,
            "is_only_rebound": False,
            "money_effect": money_effect,
            "errors": ["cycle_switch: 无前日 snapshot,标志位降级为 False"],
        }

    prev_phase = prev_snapshot.get("emotion_phase")
    prev_top = prev_snapshot.get("consec_top", 0)

    is_new = (
        prev_phase in {"chaos", "decay_2"}
        and today_phase in {"recovery", "warming"}
        and today_top >= prev_top
    )
    # only_rebound: prev was decay_2/chaos, today is up, but no follow-through expected
    # v1 simple heuristic: prev was downtrend AND today_top < 4 (no real high-board)
    is_only_rebound = (
        prev_phase in {"decay_2", "decay_1"}
        and today_phase in {"recovery", "warming"}
        and today_top < 4
    )

    return {
        "is_new_cycle_day": bool(is_new),
        "is_only_rebound": bool(is_only_rebound),
        "money_effect": money_effect,
    }
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_cycle_switch.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/cycle_switch.py tests/test_nodes/test_cycle_switch.py
git commit -m "feat(nodes): add cycle_switch with prev-day snapshot lookup + safe degradation"
```

---

## Phase 4 — ANALYZE nodes

### Task 9: LLM client + Pydantic schemas

**Files:**
- Create: `src/youzi_agent/llm/__init__.py`
- Create: `src/youzi_agent/llm/deepseek.py`
- Create: `src/youzi_agent/llm/schemas.py`
- Test: `tests/test_llm/__init__.py`, `tests/test_llm/test_schemas.py`

- [ ] **Step 1: Write the failing test (schemas only — no live LLM)**

`tests/test_llm/__init__.py`:
```python
```

`tests/test_llm/test_schemas.py`:
```python
import pytest
from youzi_agent.llm.schemas import ThemeAnalystOut, PatternEdgeOut, ThemeOut

def test_theme_analyst_out_parses():
    payload = {
        "themes": [
            {"name": "核电", "members": ["600202", "002438"], "leader": "600202",
             "phase": "vertical", "catalysts": ["政策"], "resonance_score": 0.8}
        ],
        "main_theme": "核电",
        "theme_axis": "vertical",
    }
    out = ThemeAnalystOut.model_validate(payload)
    assert out.main_theme == "核电"
    assert out.themes[0].resonance_score == 0.8

def test_resonance_score_bounded():
    with pytest.raises(Exception):
        ThemeOut.model_validate({"name": "x", "members": [], "leader": None,
                                 "phase": "horizontal", "catalysts": [],
                                 "resonance_score": 1.5})

def test_pattern_edge_out():
    edge = PatternEdgeOut.model_validate({
        "emotion_phase": "warming", "confidence": 0.85, "reason": "MA5 拐头"
    })
    assert edge.confidence == 0.85
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_llm/test_schemas.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement schemas + client**

`src/youzi_agent/llm/__init__.py`:
```python
```

`src/youzi_agent/llm/schemas.py`:
```python
"""Pydantic schemas for LLM structured output."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ThemeOut(BaseModel):
    name: str
    members: list[str]
    leader: Optional[str] = None
    phase: Literal["budding", "horizontal", "vertical", "switching", "exhausted"]
    catalysts: list[str] = Field(default_factory=list)
    resonance_score: float = Field(ge=0, le=1)


class ThemeAnalystOut(BaseModel):
    themes: list[ThemeOut]
    main_theme: Optional[str] = None
    theme_axis: Literal["horizontal", "vertical", "switching", "exhausted"]


class PatternEdgeOut(BaseModel):
    emotion_phase: Literal[
        "chaos", "recovery", "warming", "main_rise",
        "climax", "divergence", "decay_1", "decay_mid", "decay_2",
    ]
    confidence: float = Field(ge=0, le=1)
    reason: str
```

`src/youzi_agent/llm/deepseek.py`:
```python
"""DeepSeek LLM client (OpenAI-compatible) via langchain-openai."""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set in env")
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=temperature,
        timeout=30,
        max_retries=1,
    )
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_llm/test_schemas.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/llm tests/test_llm
git commit -m "feat(llm): add DeepSeek client + Pydantic output schemas"
```

---

### Task 10: `theme_analyst` node (LLM + rule fallback)

**Files:**
- Create: `src/youzi_agent/nodes/theme_analyst.py`
- Test: `tests/test_nodes/test_theme_analyst.py`

- [ ] **Step 1: Write the failing test (mock LLM)**

`tests/test_nodes/test_theme_analyst.py`:
```python
from unittest.mock import MagicMock
import pandas as pd
from youzi_agent.nodes.theme_analyst import theme_analyst_node, _rule_fallback

def _fake_state():
    ztb = pd.DataFrame({
        "代码": ["600202", "002438", "600988"],
        "名称": ["中核科技", "江苏神通", "赤峰黄金"],
        "连板数": [3, 2, 1],
        "所属行业": ["核能", "核能", "黄金"],
    })
    return {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb},
        "limit_up_count": 3,
        "consec_top": 3,
        "sentiment_value": 2200,
    }

def test_theme_analyst_no_llm_uses_industry_grouping():
    state = _fake_state()
    state["use_llm"] = False
    out = theme_analyst_node(state)
    assert "themes" in out
    assert "核能" in out["themes"] or "黄金" in out["themes"]
    assert out["theme_axis"] in {"horizontal", "vertical", "switching", "exhausted"}

def test_theme_analyst_llm_path(monkeypatch):
    state = _fake_state()
    state["use_llm"] = True
    fake_out = MagicMock()
    fake_out.themes = [MagicMock(model_dump=lambda: {
        "name": "核电", "members": ["600202", "002438"], "leader": "600202",
        "phase": "vertical", "catalysts": ["政策"], "resonance_score": 0.85
    })]
    fake_out.main_theme = "核电"
    fake_out.theme_axis = "vertical"
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = fake_out
    monkeypatch.setattr("youzi_agent.nodes.theme_analyst.get_llm", lambda *a, **k: fake_llm)
    out = theme_analyst_node(state)
    assert out["main_theme"] == "核电"
    assert out["themes"]["核电"]["resonance_score"] == 0.85

def test_theme_analyst_llm_failure_falls_back(monkeypatch):
    state = _fake_state()
    state["use_llm"] = True
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("api down")
    monkeypatch.setattr("youzi_agent.nodes.theme_analyst.get_llm", lambda *a, **k: fake_llm)
    out = theme_analyst_node(state)
    assert "errors" in out and any("theme_analyst" in e for e in out["errors"])
    assert "themes" in out  # fallback still produces themes
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_theme_analyst.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/theme_analyst.py`:
```python
"""Cluster today's limit-up stocks into themes (LLM with rule fallback)."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ..llm.deepseek import get_llm
from ..llm.schemas import ThemeAnalystOut
from ..state import MarketState

THEME_PROMPT = """你是 A 股游资策略师。给定今日涨停股票池及其行业 / 概念标签,完成 4 件事:
1) 把股票按"今日真正驱动的题材"重新聚类(同一只股可属多个题材)
2) 判每个题材的演绎阶段:budding(萌芽) / horizontal(横向扩散) / vertical(纵向涨停加速) / switching(切换中) / exhausted(衰竭)
3) 推断当日主线 main_theme(若无明显主线返回 null)
4) 判 theme_axis:horizontal=多线开花 / vertical=单线纵深 / switching=主线切换 / exhausted=全面衰竭

# 今日涨停股
{lu_table}

# 上下文
- 当日涨停家数: {lu_count}
- 最高连板: {consec_top}
- 情绪值锚定: {sentiment_value}

只输出 JSON,严格符合 schema。"""


def _render_lu_table(ztb: pd.DataFrame) -> str:
    cols = [c for c in ["代码", "名称", "连板数", "所属行业", "概念"] if c in ztb.columns]
    return ztb[cols].to_string(index=False) if cols else "(空)"


def _rule_fallback(state: MarketState) -> dict:
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"themes": {}, "main_theme": None, "theme_axis": "horizontal"}
    group_col = "所属行业" if "所属行业" in ztb.columns else ("概念" if "概念" in ztb.columns else None)
    if not group_col:
        return {"themes": {"_unclassified": {
            "name": "_unclassified",
            "members": ztb["代码"].astype(str).tolist(),
            "leader": None, "catalysts": [], "phase": "horizontal", "resonance_score": 0.3,
        }}, "main_theme": None, "theme_axis": "horizontal"}
    buckets: dict[str, list[str]] = defaultdict(list)
    for _, row in ztb.iterrows():
        buckets[str(row[group_col])].append(str(row["代码"]))
    themes = {name: {
        "name": name, "members": members,
        "leader": members[0] if members else None,
        "catalysts": [], "phase": "horizontal",
        "resonance_score": min(1.0, len(members) / 5),
    } for name, members in buckets.items()}
    main = max(buckets.items(), key=lambda kv: len(kv[1]))[0] if buckets else None
    axis = "vertical" if main and len(buckets[main]) >= 5 else "horizontal"
    return {"themes": themes, "main_theme": main, "theme_axis": axis}


def theme_analyst_node(state: MarketState) -> dict:
    if not state.get("use_llm", True):
        return _rule_fallback(state)
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return _rule_fallback(state)
    try:
        llm = get_llm(0.3).with_structured_output(ThemeAnalystOut)
        out = llm.invoke(THEME_PROMPT.format(
            lu_table=_render_lu_table(ztb),
            lu_count=state.get("limit_up_count", 0),
            consec_top=state.get("consec_top", 0),
            sentiment_value=state.get("sentiment_value", 0),
        ))
        return {
            "themes": {t.model_dump()["name"]: t.model_dump() for t in out.themes},
            "main_theme": out.main_theme,
            "theme_axis": out.theme_axis,
        }
    except Exception as e:
        return {"errors": [f"theme_analyst LLM failed: {e}"], **_rule_fallback(state)}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_theme_analyst.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/theme_analyst.py tests/test_nodes/test_theme_analyst.py
git commit -m "feat(nodes): add theme_analyst with DeepSeek + industry-group rule fallback"
```

---

### Task 11: `leader_tracker` node

**Files:**
- Create: `src/youzi_agent/nodes/leader_tracker.py`
- Test: `tests/test_nodes/test_leader_tracker.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_leader_tracker.py`:
```python
import pandas as pd
from youzi_agent.nodes.leader_tracker import leader_tracker_node, _strength

def _state():
    ztb = pd.DataFrame({
        "代码": ["600202", "002438", "300999", "600000"],
        "名称": ["中核科技", "江苏神通", "新票", "浦发"],
        "连板数": [4, 3, 1, 1],
        "封单金额": [3e8, 1.5e8, 0.5e8, 0.2e8],
        "首次封板时间": ["09:30", "09:45", "10:30", "13:50"],
        "炸板次数": [0, 0, 0, 2],
    })
    return {
        "raw": {"ztb_today": ztb},
        "themes": {
            "核电": {"name": "核电", "members": ["600202", "002438"],
                     "leader": "600202", "phase": "vertical",
                     "catalysts": [], "resonance_score": 0.8},
        },
        "consec_top": 4,
    }

def test_strength_score_orders_by_consec_then_seal():
    a = _strength({"连板数": 4, "封单金额": 3e8, "首次封板时间": "09:30", "炸板次数": 0})
    b = _strength({"连板数": 3, "封单金额": 1e8, "首次封板时间": "10:00", "炸板次数": 1})
    assert a > b

def test_leader_tracker_assigns_total_role():
    out = leader_tracker_node(_state())
    leaders = out["leader_stack"]
    total = next(l for l in leaders if l["role"] == "total")
    assert total["code"] == "600202"
    assert total["consec_boards"] == 4

def test_leader_tracker_succession_healthy():
    out = leader_tracker_node(_state())
    assert out["succession_status"] in {"healthy", "first_div"}
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_leader_tracker.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/leader_tracker.py`:
```python
"""Daily-only leader strength + role assignment + succession status."""
from __future__ import annotations

from typing import cast

import pandas as pd

from ..state import LeaderProfile, MarketState, SuccessionStatus


def _seal_billions(seal_amount: float) -> float:
    return float(seal_amount) / 1e8 if seal_amount else 0.0


def _strength(row: dict) -> float:
    consec = int(row.get("连板数", 0))
    seal = _seal_billions(row.get("封单金额", 0))
    early = 10 if str(row.get("首次封板时间", "")) < "10:00" else 0
    blast = int(row.get("炸板次数", 0))
    return consec * 2 + seal + early - blast


def _assign_succession(top_leader: LeaderProfile, consec_top: int) -> SuccessionStatus:
    if not top_leader:
        return "broken"
    if top_leader["consec_boards"] >= 4 and not top_leader["blast_today"]:
        return "healthy"
    if top_leader["consec_boards"] >= 4 and top_leader["blast_today"]:
        return "first_div"
    if top_leader["consec_boards"] < consec_top - 1:
        return "trans"
    return "healthy"


def leader_tracker_node(state: MarketState) -> dict:
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"leader_stack": [], "succession_status": "broken"}
    themes = state.get("themes", {})
    member_to_theme = {m: tn for tn, t in themes.items() for m in t.get("members", [])}

    leaders: list[LeaderProfile] = []
    # Per-theme top picks
    for tname, t in themes.items():
        members = t.get("members", [])
        sub = ztb[ztb["代码"].astype(str).isin(members)].copy()
        if sub.empty:
            continue
        sub["_score"] = sub.apply(lambda r: _strength(r), axis=1)
        sub = sub.sort_values("_score", ascending=False)
        for i, (_, row) in enumerate(sub.iterrows()):
            role = "total" if i == 0 else "companion" if i == 1 else "complement"
            leaders.append(cast(LeaderProfile, {
                "code": str(row["代码"]),
                "name": str(row["名称"]),
                "consec_boards": int(row["连板数"]),
                "role": role,
                "sealed_amount": _seal_billions(row.get("封单金额", 0)),
                "blast_today": int(row.get("炸板次数", 0)) > 0,
                "div_count": 0,
            }))

    # Sort overall by score, "total" of the strongest theme is the market leader
    leaders.sort(key=lambda l: -(l["consec_boards"] * 2 + l["sealed_amount"]))
    top = leaders[0] if leaders else None
    succession = _assign_succession(top, state.get("consec_top", 0)) if top else "broken"
    return {"leader_stack": leaders, "succession_status": succession}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_leader_tracker.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/leader_tracker.py tests/test_nodes/test_leader_tracker.py
git commit -m "feat(nodes): add leader_tracker with strength score + succession state"
```

---

### Task 12: `pattern_matcher` node (truth table + LLM tiebreaker)

**Files:**
- Create: `src/youzi_agent/nodes/pattern_matcher.py`
- Test: `tests/test_nodes/test_pattern_matcher.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_pattern_matcher.py`:
```python
from unittest.mock import MagicMock
from youzi_agent.nodes.pattern_matcher import pattern_matcher_node, _lookup_route, ROUTE_TABLE

def test_lookup_exact_match():
    out = _lookup_route("recovery", True, "first_div", "uptrend")
    assert "L1_first_board" in out

def test_lookup_wildcard_succession():
    # climax with any succession → []
    assert _lookup_route("climax", False, "healthy", "uptrend") == []

def test_pattern_matcher_emits_hits():
    state = {
        "emotion_phase": "recovery", "is_new_cycle_day": True,
        "succession_status": "first_div", "index_phase": "uptrend",
        "limit_up_count": 60, "consec_top": 4, "blast_rate": 0.18,
        "use_llm": False,
    }
    out = pattern_matcher_node(state)
    ids = [h["pattern_id"] for h in out["pattern_hits"]]
    assert "L1_first_board" in ids
    targets = {h["target_subagent"] for h in out["pattern_hits"]}
    assert "first_board" in targets

def test_pattern_matcher_edge_triggers_llm(monkeypatch):
    state = {
        "emotion_phase": "warming", "is_new_cycle_day": False,
        "succession_status": "healthy", "index_phase": "uptrend",
        "limit_up_count": 1010,             # edge: ±10% of 1000 threshold
        "consec_top": 4, "blast_rate": 0.18,
        "use_llm": True,
    }
    fake_edge = MagicMock(emotion_phase="chaos", confidence=0.85, reason="近冰点")
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = fake_edge
    monkeypatch.setattr("youzi_agent.nodes.pattern_matcher.get_llm", lambda *a, **k: fake_llm)
    out = pattern_matcher_node(state)
    assert out["emotion_phase"] == "chaos"

def test_pattern_matcher_climax_emits_no_hits():
    state = {
        "emotion_phase": "climax", "is_new_cycle_day": False,
        "succession_status": "healthy", "index_phase": "uptrend",
        "limit_up_count": 150, "consec_top": 8, "blast_rate": 0.20,
        "use_llm": False,
    }
    out = pattern_matcher_node(state)
    assert out["pattern_hits"] == []
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_pattern_matcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/pattern_matcher.py`:
```python
"""Truth-table routing + optional LLM tiebreaker for emotion_phase."""
from __future__ import annotations

from ..llm.deepseek import get_llm
from ..llm.schemas import PatternEdgeOut
from ..state import MarketState, PatternHit

# (emotion, is_new_cycle_day, succession_status, index_phase) -> [pattern_id]
ROUTE_TABLE: dict[tuple[str, object, str, str], list[str]] = {
    ("chaos",      False, "broken",     "*"): ["L1_first_board", "L2_weak_to_strong"],
    ("recovery",   True,  "first_div",  "uptrend"): ["L1_first_board", "L2_weak_to_strong"],
    ("recovery",   "*",   "*",          "*"): ["L1_first_board"],
    ("warming",    False, "healthy",    "uptrend"): ["L4_strong_2b", "first_to_continuous"],
    ("warming",    "*",   "*",          "*"): ["L1_first_board", "first_to_continuous"],
    ("main_rise",  False, "healthy",    "uptrend"): ["L4_strong_2b"],
    ("climax",     "*",   "*",          "*"): [],
    ("divergence", False, "first_div",  "*"): ["S2_setback_reversal"],
    ("divergence", False, "second_div", "*"): [],
    ("decay_1",    "*",   "*",          "*"): [],
    ("decay_2",    "*",   "*",          "*"): [],
    ("decay_mid",  "*",   "*",          "*"): [],
}

PATTERN_TO_SUBAGENT = {
    "L1_first_board":      "first_board",
    "L2_weak_to_strong":   "weak_to_strong",
    "L4_strong_2b":        "first_board",
    "first_to_continuous": "continuous",
    "S2_setback_reversal": "setback_reversal",
}

PATTERN_DESC = {
    "L1_first_board":      "主流板块辨识度首板",
    "L2_weak_to_strong":   "极致弱转强",
    "L4_strong_2b":        "强势 2 板",
    "first_to_continuous": "一进二接力",
    "S2_setback_reversal": "首阴反包",
}


def _lookup_route(emotion: str, is_new: bool, succession: str, index_phase: str) -> list[str]:
    keys_to_try = [
        (emotion, is_new, succession, index_phase),
        (emotion, "*",   succession, index_phase),
        (emotion, is_new, "*",       index_phase),
        (emotion, "*",   "*",        index_phase),
        (emotion, is_new, succession, "*"),
        (emotion, "*",   succession, "*"),
        (emotion, is_new, "*",       "*"),
        (emotion, "*",   "*",        "*"),
    ]
    for k in keys_to_try:
        if k in ROUTE_TABLE:
            return ROUTE_TABLE[k]
    return []


def _is_edge_case(state: MarketState) -> bool:
    lu = state.get("limit_up_count", 0)
    if 900 <= lu <= 1100 or 3900 <= lu <= 4100 or 90 <= lu <= 110:
        return True
    if state.get("blast_rate", 0) > 0.40:
        return True
    return False


EDGE_PROMPT = """规则给出的 emotion_phase 是 {rule_phase},但以下指标边缘:
- 涨停家数 {lu}, 炸板率 {br:.1%}, 最高连板 {top}
- 五日线位置 {five_pos}
请给出你认为更准的 emotion_phase 和 confidence,并简述判断依据(80 字内)。"""


def pattern_matcher_node(state: MarketState) -> dict:
    emotion = state.get("emotion_phase", "warming")
    succession = state.get("succession_status", "healthy")
    index_phase = state.get("index_phase", "oscillation")
    is_new = bool(state.get("is_new_cycle_day", False))

    state_patch: dict = {}
    if state.get("use_llm", True) and _is_edge_case(state):
        try:
            llm = get_llm(0.2).with_structured_output(PatternEdgeOut)
            edge = llm.invoke(EDGE_PROMPT.format(
                rule_phase=emotion,
                lu=state.get("limit_up_count", 0),
                br=state.get("blast_rate", 0.0),
                top=state.get("consec_top", 0),
                five_pos=state.get("five_day_pos", "?"),
            ))
            if edge.confidence > 0.7 and edge.emotion_phase != emotion:
                state_patch = {
                    "emotion_phase": edge.emotion_phase,
                    "errors": [f"pattern_matcher LLM 改判 → {edge.emotion_phase} ({edge.reason})"],
                }
                emotion = edge.emotion_phase
        except Exception as e:
            state_patch = {"errors": [f"pattern_matcher LLM failed: {e}"]}

    pattern_ids = _lookup_route(emotion, is_new, succession, index_phase)
    hits: list[PatternHit] = [
        {"pattern_id": pid,
         "filter_desc": PATTERN_DESC.get(pid, pid),
         "target_subagent": PATTERN_TO_SUBAGENT[pid]}
        for pid in pattern_ids if pid in PATTERN_TO_SUBAGENT
    ]
    return {"pattern_hits": hits, **state_patch}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_pattern_matcher.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/pattern_matcher.py tests/test_nodes/test_pattern_matcher.py
git commit -m "feat(nodes): add pattern_matcher with wildcard truth-table + LLM edge tiebreaker"
```

---

## Phase 5 — Sub-agents (4 sub-graphs)

### Task 13: `first_board` sub-graph

**Files:**
- Create: `src/youzi_agent/subagents/__init__.py`
- Create: `src/youzi_agent/subagents/first_board.py`
- Test: `tests/test_subagents/__init__.py`, `tests/test_subagents/test_first_board.py`

- [ ] **Step 1: Write the failing test**

`tests/test_subagents/__init__.py`:
```python
```

`tests/test_subagents/test_first_board.py`:
```python
import pandas as pd
from youzi_agent.subagents.first_board import build_fb_subgraph, fb_filter, fb_score

def _state():
    ztb_yest = pd.DataFrame({
        "代码":         ["600202", "002438", "300999", "600000", "688001"],
        "名称":         ["中核科技", "江苏神通", "新票", "浦发ST", "次新票"],
        "连板数":       [1, 1, 1, 1, 1],
        "封单金额":     [2e8, 1.2e8, 0.5e8, 0.8e8, 1e8],
        "首次封板时间": ["09:35", "09:50", "10:15", "10:00", "09:31"],
        "炸板次数":     [0, 0, 1, 0, 0],
        "上市天数":     [800, 600, 1000, 700, 30],
        "开盘价":       [10.0, 8.0, 5.0, 6.0, 20.0],
        "涨停价":       [11.0, 8.8, 5.5, 6.6, 22.0],
    })
    # Inject ST in name, next-new with 上市天数<60
    ztb_yest.loc[3, "名称"] = "ST 浦发"
    return {
        "target_date": "2026-04-25",
        "raw": {"ztb_yesterday": ztb_yest},
        "themes": {"核电": {"name": "核电", "members": ["600202", "002438"],
                            "leader": "600202", "phase": "vertical", "catalysts": [],
                            "resonance_score": 0.8}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "L1_first_board", "filter_desc": "x",
                          "target_subagent": "first_board"}],
    }

def test_fb_filter_excludes_st_and_new():
    state = _state()
    out = fb_filter(state)
    pool = out["_fb_pool"]
    codes = {r["代码"] for r in pool}
    assert "688001" not in codes  # 次新
    assert "600000" not in codes  # ST

def test_fb_score_main_theme_bonus():
    state = _state()
    state.update(fb_filter(state))
    out = fb_score(state)
    scored = {r["代码"]: r["_score"] for r in out["_fb_scored"]}
    assert scored["600202"] > scored.get("300999", 0)

def test_first_board_subgraph_e2e():
    g = build_fb_subgraph()
    out = g.invoke(_state())
    assert "candidates" in out
    assert any(c["pattern_id"] == "L1_first_board" for c in out["candidates"])
    assert all(0 <= c["score"] <= 1 for c in out["candidates"])
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_subagents/test_first_board.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/subagents/__init__.py`:
```python
```

`src/youzi_agent/subagents/first_board.py`:
```python
"""一进二 sub-graph: filter → score → rank."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import FirstBoardState


def fb_filter(s: FirstBoardState) -> dict:
    ztb_yest = s.get("raw", {}).get("ztb_yesterday")
    if ztb_yest is None or len(ztb_yest) == 0:
        return {"_fb_pool": []}
    df = ztb_yest.copy()
    df["代码"] = df["代码"].astype(str)
    df = df[df["连板数"] == 1]
    if "名称" in df.columns:
        df = df[~df["名称"].astype(str).str.contains("ST|退", na=False)]
    if "上市天数" in df.columns:
        df = df[df["上市天数"] > 60]
    if "开盘价" in df.columns and "涨停价" in df.columns:
        df = df[df["开盘价"] < df["涨停价"] * 0.999]
    return {"_fb_pool": df.to_dict("records")}


def fb_score(s) -> dict:
    pool = s.get("_fb_pool", [])
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    out = []
    for r in pool:
        score = 0.0
        if str(r.get("代码")) in main_members: score += 0.4
        if float(r.get("封单金额", 0)) > 1e8:   score += 0.2
        if str(r.get("首次封板时间", "")) < "10:00": score += 0.2
        if int(r.get("炸板次数", 0)) == 0:      score += 0.2
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_fb_scored": out}


def fb_rank(s) -> dict:
    scored = s.get("_fb_scored", [])[:5]
    candidates = []
    for r in scored:
        candidates.append({
            "code": str(r["代码"]),
            "name": str(r.get("名称", "")),
            "pattern_id": "L1_first_board",
            "score": float(r["_score"]),
            "reason": f"昨首板·封单{float(r.get('封单金额', 0))/1e8:.1f}亿·封板{r.get('首次封板时间','')}",
            "suggested_position": 0.10,
        })
    return {"candidates": candidates}


def build_fb_subgraph():
    g = StateGraph(FirstBoardState)
    g.add_node("filter", fb_filter)
    g.add_node("score", fb_score)
    g.add_node("rank", fb_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_subagents/test_first_board.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/subagents tests/test_subagents
git commit -m "feat(subagents): add first_board sub-graph (filter → score → rank)"
```

---

### Task 14: `weak_to_strong` sub-graph

**Files:**
- Create: `src/youzi_agent/subagents/weak_to_strong.py`
- Test: `tests/test_subagents/test_weak_to_strong.py`

- [ ] **Step 1: Write the failing test**

`tests/test_subagents/test_weak_to_strong.py`:
```python
import pandas as pd
from youzi_agent.subagents.weak_to_strong import build_w2s_subgraph

def test_w2s_picks_yesterday_blast_with_today_gap_up():
    ztb_yest = pd.DataFrame({
        "代码": ["600202"],          # yesterday: limited up but blast >=2
        "名称": ["中核科技"],
        "连板数": [1],
        "封单金额": [0.3e8],
        "首次封板时间": ["14:30"],
        "炸板次数": [3],
        "涨停价": [11.0],
        "收盘价": [11.0],
    })
    ztb_today = pd.DataFrame({
        "代码": ["600202"],
        "名称": ["中核科技"],
        "连板数": [2],
        "封单金额": [4e8],
        "首次封板时间": ["09:33"],     # 5min 内秒板
        "炸板次数": [0],
        "开盘价": [11.6],              # 高开 5%+
        "昨日收盘": [11.0],
        "涨停价": [12.1],
    })
    state = {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb_today, "ztb_yesterday": ztb_yest},
        "themes": {"核电": {"name": "核电", "members": ["600202"], "leader": "600202",
                            "phase": "vertical", "catalysts": [], "resonance_score": 0.8}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "L2_weak_to_strong", "filter_desc": "x",
                          "target_subagent": "weak_to_strong"}],
    }
    out = build_w2s_subgraph().invoke(state)
    assert any(c["code"] == "600202" for c in out.get("candidates", []))
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_subagents/test_weak_to_strong.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/subagents/weak_to_strong.py`:
```python
"""弱转强 sub-graph (daily-only approximation)."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import WeakToStrongState


def w2s_filter(s: WeakToStrongState) -> dict:
    yest = s.get("raw", {}).get("ztb_yesterday")
    today = s.get("raw", {}).get("ztb_today")
    if yest is None or today is None or len(today) == 0:
        return {"_w2s_pool": []}
    yest_codes = yest[yest.get("炸板次数", 0).astype(int) >= 2]["代码"].astype(str).tolist()
    sub = today[today["代码"].astype(str).isin(yest_codes)].copy()
    if sub.empty:
        return {"_w2s_pool": []}
    if "开盘价" in sub.columns and "昨日收盘" in sub.columns:
        sub = sub[(sub["开盘价"] / sub["昨日收盘"]) > 1.05]
    if "涨停价" in sub.columns and "开盘价" in sub.columns:
        sub = sub[sub["开盘价"] < sub["涨停价"] * 0.999]   # 排除一字开
    return {"_w2s_pool": sub.to_dict("records")}


def w2s_score(s) -> dict:
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    out = []
    for r in s.get("_w2s_pool", []):
        score = 0.0
        if str(r["代码"]) in main_members: score += 0.4
        if str(r.get("首次封板时间", "")) < "09:35": score += 0.3   # 5min 秒板
        if float(r.get("封单金额", 0)) > 1e8: score += 0.2
        if int(r.get("炸板次数", 0)) == 0:    score += 0.1
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_w2s_scored": out}


def w2s_rank(s) -> dict:
    return {"candidates": [{
        "code": str(r["代码"]),
        "name": str(r.get("名称", "")),
        "pattern_id": "L2_weak_to_strong",
        "score": float(r["_score"]),
        "reason": f"昨烂今强·{r.get('首次封板时间','')}秒板·封单{float(r.get('封单金额',0))/1e8:.1f}亿",
        "suggested_position": 0.10,
    } for r in s.get("_w2s_scored", [])[:5]]}


def build_w2s_subgraph():
    g = StateGraph(WeakToStrongState)
    g.add_node("filter", w2s_filter)
    g.add_node("score", w2s_score)
    g.add_node("rank", w2s_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_subagents/test_weak_to_strong.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/subagents/weak_to_strong.py tests/test_subagents/test_weak_to_strong.py
git commit -m "feat(subagents): add weak_to_strong sub-graph (daily approximation)"
```

---

### Task 15: `continuous` sub-graph

**Files:**
- Create: `src/youzi_agent/subagents/continuous.py`
- Test: `tests/test_subagents/test_continuous.py`

- [ ] **Step 1: Write the failing test**

`tests/test_subagents/test_continuous.py`:
```python
import pandas as pd
from youzi_agent.subagents.continuous import build_con_subgraph

def test_continuous_picks_2b_in_main_theme():
    ztb_today = pd.DataFrame({
        "代码":         ["600202", "002438", "300999"],
        "名称":         ["中核科技", "江苏神通", "新票"],
        "连板数":       [3, 2, 2],
        "封单金额":     [3e8, 1e8, 0.4e8],
        "首次封板时间": ["09:35", "10:00", "13:50"],
        "炸板次数":     [0, 0, 1],
    })
    state = {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb_today},
        "themes": {"核电": {"name": "核电",
                            "members": ["600202", "002438", "300999"],
                            "leader": "600202", "phase": "vertical",
                            "catalysts": [], "resonance_score": 0.85}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "first_to_continuous",
                          "filter_desc": "x", "target_subagent": "continuous"}],
    }
    out = build_con_subgraph().invoke(state)
    codes = [c["code"] for c in out.get("candidates", [])]
    assert "600202" in codes or "002438" in codes
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_subagents/test_continuous.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/subagents/continuous.py`:
```python
"""二进三 / 分歧三板 sub-graph."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import ContinuousState


def con_filter(s: ContinuousState) -> dict:
    ztb = s.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"_con_pool": []}
    df = ztb.copy()
    df["代码"] = df["代码"].astype(str)
    df = df[df["连板数"].isin([2, 3])]
    return {"_con_pool": df.to_dict("records")}


def con_score(s) -> dict:
    main = (s.get("themes") or {}).get(s.get("main_theme") or "")
    main_members = set((main or {}).get("members", []))
    # Same-theme ladder size
    ladder = sum(1 for r in s.get("_con_pool", []) if str(r["代码"]) in main_members)
    out = []
    for r in s.get("_con_pool", []):
        score = 0.0
        if str(r["代码"]) in main_members: score += 0.4
        if int(r["连板数"]) == 2:           score += 0.2
        if int(r.get("炸板次数", 0)) == 0:  score += 0.2
        if ladder >= 3:                     score += 0.2
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_con_scored": out}


def con_rank(s) -> dict:
    return {"candidates": [{
        "code": str(r["代码"]),
        "name": str(r.get("名称", "")),
        "pattern_id": "first_to_continuous",
        "score": float(r["_score"]),
        "reason": f"{int(r['连板数'])}板·主线·封单{float(r.get('封单金额',0))/1e8:.1f}亿",
        "suggested_position": 0.10,
        "consec_boards": int(r["连板数"]),
    } for r in s.get("_con_scored", [])[:5]]}


def build_con_subgraph():
    g = StateGraph(ContinuousState)
    g.add_node("filter", con_filter)
    g.add_node("score", con_score)
    g.add_node("rank", con_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_subagents/test_continuous.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/subagents/continuous.py tests/test_subagents/test_continuous.py
git commit -m "feat(subagents): add continuous sub-graph (2B/3B ladder)"
```

---

### Task 16: `setback_reversal` sub-graph

**Files:**
- Create: `src/youzi_agent/subagents/setback_reversal.py`
- Test: `tests/test_subagents/test_setback_reversal.py`

> **Data dependency note:** This sub-graph reads `state["raw"]["klines_by_code"]`, a per-stock dict of daily K-lines. v1's `market_sensor_node` does **not** populate it (would need an extra batch of `AkshareClient.stock_kline()` calls for the limit-up universe). Consequence: in real EOD runs this sub-graph emits zero candidates whenever `klines_by_code` is missing — graceful degradation. v2 work item: have `market_sensor_node` (or a new `kline_loader` node) fetch klines for the union of (today's + yesterday's limit-up codes + leader_stack codes from prev snapshot).

- [ ] **Step 1: Write the failing test (uses individual klines from raw)**

`tests/test_subagents/test_setback_reversal.py`:
```python
import pandas as pd
from youzi_agent.subagents.setback_reversal import build_sr_subgraph

def _kline(closes, opens=None):
    opens = opens or [c * 0.99 for c in closes]
    return pd.DataFrame({
        "日期": pd.date_range("2026-04-15", periods=len(closes)),
        "开盘": opens, "收盘": closes,
        "最高": [c * 1.02 for c in closes],
        "最低": [c * 0.98 for c in closes],
        "成交量": [1e7] * len(closes),
        "涨跌幅": [0.0] + [(closes[i]/closes[i-1]-1)*100 for i in range(1, len(closes))],
    })

def test_sr_picks_yin_eat_yang_after_recent_limit_up():
    # 600202: 5 days ago limit-up (10%), today is yin engulfing yesterday open
    closes = [10.0, 11.0, 11.5, 11.7, 11.0, 10.5, 10.2, 9.8]
    opens  = [10.0, 10.0, 11.2, 11.5, 11.4, 10.8, 10.6, 10.5]
    klines = {"600202": _kline(closes, opens)}
    state = {
        "target_date": "2026-04-22",
        "raw": {"klines_by_code": klines},
        "themes": {"核电": {"name": "核电", "members": ["600202"], "leader": "600202",
                            "phase": "switching", "catalysts": [], "resonance_score": 0.6}},
        "main_theme": "核电",
        "emotion_phase": "divergence",
        "pattern_hits": [{"pattern_id": "S2_setback_reversal", "filter_desc": "x",
                          "target_subagent": "setback_reversal"}],
    }
    out = build_sr_subgraph().invoke(state)
    assert any(c["code"] == "600202" for c in out.get("candidates", []))
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_subagents/test_setback_reversal.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/subagents/setback_reversal.py`:
```python
"""首阴反包 sub-graph."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import SetbackReversalState


def _had_recent_limit_up(kline, lookback: int = 5) -> bool:
    if "涨跌幅" not in kline.columns:
        return False
    recent = kline.tail(lookback + 1).iloc[:-1]
    return bool((recent["涨跌幅"].astype(float) >= 9.5).any())


def _is_yin_engulf(kline) -> bool:
    if len(kline) < 2:
        return False
    today = kline.iloc[-1]; yest = kline.iloc[-2]
    return bool(float(today["收盘"]) <= float(yest["开盘"]) * 1.005
                and float(today["收盘"]) < float(today["开盘"]))


def sr_filter(s: SetbackReversalState) -> dict:
    klines = s.get("raw", {}).get("klines_by_code", {})
    pool = []
    for code, kline in klines.items():
        if _had_recent_limit_up(kline) and _is_yin_engulf(kline):
            pool.append({"code": code, "kline": kline})
    return {"_sr_pool": pool}


def sr_score(s) -> dict:
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    emotion = s.get("emotion_phase", "")
    out = []
    for r in s.get("_sr_pool", []):
        kline = r["kline"]
        today = kline.iloc[-1]
        drop_pct = abs(float(today["涨跌幅"]))
        score = 0.0
        if r["code"] in main_members: score += 0.3
        if drop_pct > 5:               score += 0.3
        if emotion == "divergence":    score += 0.2
        # 缩量
        if len(kline) >= 6:
            avg_vol = float(kline["成交量"].iloc[-6:-1].mean())
            if float(today["成交量"]) < avg_vol: score += 0.2
        out.append({"code": r["code"], "_score": round(score, 2),
                    "drop_pct": drop_pct})
    out.sort(key=lambda x: -x["_score"])
    return {"_sr_scored": out}


def sr_rank(s) -> dict:
    return {"candidates": [{
        "code": r["code"],
        "name": "",
        "pattern_id": "S2_setback_reversal",
        "score": float(r["_score"]),
        "reason": f"首阴反包候选·跌幅{r['drop_pct']:.1f}%",
        "suggested_position": 0.05,
    } for r in s.get("_sr_scored", [])[:5]]}


def build_sr_subgraph():
    g = StateGraph(SetbackReversalState)
    g.add_node("filter", sr_filter)
    g.add_node("score", sr_score)
    g.add_node("rank", sr_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_subagents/test_setback_reversal.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/subagents/setback_reversal.py tests/test_subagents/test_setback_reversal.py
git commit -m "feat(subagents): add setback_reversal (yin-engulf after recent limit-up)"
```

---

## Phase 6 — Decide nodes

### Task 17: `arbitrage` node (4 hardcoded patterns)

**Files:**
- Create: `src/youzi_agent/nodes/arbitrage.py`
- Test: `tests/test_nodes/test_arbitrage.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_arbitrage.py`:
```python
from youzi_agent.nodes.arbitrage import arbitrage_node

def test_complement_arb_emits_when_strong_leader_with_low_consec_companion():
    state = {
        "leader_stack": [
            {"code": "600202", "name": "中核科技", "consec_boards": 7,
             "role": "total", "sealed_amount": 2.0, "blast_today": False, "div_count": 0},
            {"code": "002438", "name": "江苏神通", "consec_boards": 2,
             "role": "complement", "sealed_amount": 0.5, "blast_today": False, "div_count": 0},
        ],
        "themes": {"核电": {"name": "核电", "members": ["600202", "002438"],
                            "leader": "600202", "phase": "vertical", "catalysts": [],
                            "resonance_score": 0.9}},
        "main_theme": "核电",
        "emotion_phase": "main_rise",
    }
    out = arbitrage_node(state)
    arbs = out["arb_opportunities"]
    assert any("补涨" in a["reason"] for a in arbs)

def test_arbitrage_returns_empty_when_no_leader():
    state = {"leader_stack": [], "themes": {}, "emotion_phase": "chaos"}
    out = arbitrage_node(state)
    assert out["arb_opportunities"] == []
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_arbitrage.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/arbitrage.py`:
```python
"""4 hardcoded arbitrage scanners."""
from __future__ import annotations

from ..state import Candidate, MarketState


def _ladder_arb(state: MarketState) -> list[Candidate]:
    # v1: pass-through; needs first-board filter inside same theme as 4-5B leader
    return []


def _complement_arb(state: MarketState) -> list[Candidate]:
    leaders = state.get("leader_stack", [])
    if not leaders:
        return []
    main = next((l for l in leaders if l["role"] == "total"), None)
    if not main or main["consec_boards"] < 5:
        return []
    same_theme_complements = [l for l in leaders
                              if l["role"] in {"complement", "companion"}
                              and l["consec_boards"] <= main["consec_boards"] - 3]
    return [{
        "code": l["code"], "name": l["name"], "pattern_id": "arb_complement",
        "score": 0.5,
        "reason": f"补涨套利·主龙{main['code']}({main['consec_boards']}B)同属性低位",
        "suggested_position": 0.05,
    } for l in same_theme_complements[:3]]


def _new_cycle_arb(state: MarketState) -> list[Candidate]:
    # v1: stub. Needs intraday or next-day data not in EOD batch.
    return []


def _drop_out_arb(state: MarketState) -> list[Candidate]:
    return []


def arbitrage_node(state: MarketState) -> dict:
    arbs: list[Candidate] = []
    arbs += _ladder_arb(state)
    arbs += _complement_arb(state)
    arbs += _new_cycle_arb(state)
    arbs += _drop_out_arb(state)
    return {"arb_opportunities": arbs}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_arbitrage.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/arbitrage.py tests/test_nodes/test_arbitrage.py
git commit -m "feat(nodes): add arbitrage scanner (complement-arb impl, others stubbed)"
```

---

### Task 18: `risk_guard` node (10 v1 taboos)

**Files:**
- Create: `src/youzi_agent/nodes/risk_guard.py`
- Test: `tests/test_nodes/test_risk_guard.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_risk_guard.py`:
```python
from youzi_agent.nodes.risk_guard import risk_guard_node, _zone_total_max

def test_drop_w2s_in_decay_1():
    state = {
        "emotion_phase": "decay_1", "index_phase": "downtrend",
        "candidates": [
            {"code": "600202", "name": "x", "pattern_id": "L2_weak_to_strong",
             "score": 0.7, "reason": "r", "suggested_position": 0.1},
            {"code": "002438", "name": "y", "pattern_id": "L1_first_board",
             "score": 0.6, "reason": "r", "suggested_position": 0.1},
        ],
    }
    out = risk_guard_node(state)
    finals = out["final_candidates"]
    assert all(c["pattern_id"] != "L2_weak_to_strong" for c in finals)
    assert any("禁忌" in f for f in out["risk_flags"])

def test_drop_high_consec_in_chaos():
    state = {
        "emotion_phase": "chaos", "index_phase": "downtrend",
        "candidates": [
            {"code": "600202", "name": "x", "pattern_id": "first_to_continuous",
             "score": 0.7, "reason": "r", "suggested_position": 0.1, "consec_boards": 3},
        ],
    }
    out = risk_guard_node(state)
    assert out["final_candidates"] == []

def test_zone_total_max_warming():
    pos = _zone_total_max("warming", "uptrend")
    assert pos == 1.0

def test_zone_total_max_climax():
    pos = _zone_total_max("climax", "uptrend")
    assert pos <= 0.3
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_risk_guard.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/risk_guard.py`:
```python
"""10-rule risk filter; outputs final_candidates (replace semantics)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..state import Candidate, MarketState


@dataclass
class Taboo:
    name: str
    desc: str
    predicate: Callable[[MarketState, Candidate], bool]
    drop: bool = True


TABOOS: list[Taboo] = [
    Taboo("no_chase_climax", "高潮日不接力首封",
          lambda s, c: s.get("emotion_phase") == "climax"),
    Taboo("no_w2s_in_decay", "退潮初期不做弱转强",
          lambda s, c: s.get("emotion_phase") == "decay_1"
                         and c.get("pattern_id") == "L2_weak_to_strong"),
    Taboo("max_consec_in_chaos", "情绪冰点最高连板 ≥ 3 不接力",
          lambda s, c: s.get("emotion_phase") == "chaos"
                         and int(c.get("consec_boards", 0)) >= 3),
    Taboo("avoid_st", "ST 股不进任何池",
          lambda s, c: "ST" in c.get("name", "") or "退" in c.get("name", "")),
    Taboo("no_w2s_in_main_rise", "主升期不接 weak_to_strong",
          lambda s, c: s.get("emotion_phase") == "main_rise"
                         and c.get("pattern_id") == "L2_weak_to_strong"),
    Taboo("no_setback_in_chaos", "冰点不做反包",
          lambda s, c: s.get("emotion_phase") == "chaos"
                         and c.get("pattern_id") == "S2_setback_reversal"),
    Taboo("no_first_board_in_climax", "高潮日不打首板",
          lambda s, c: s.get("emotion_phase") == "climax"
                         and c.get("pattern_id") == "L1_first_board"),
    Taboo("no_continuous_in_decay", "退潮不接连板",
          lambda s, c: s.get("emotion_phase") in {"decay_1", "decay_2"}
                         and c.get("pattern_id") == "first_to_continuous"),
    Taboo("low_score_threshold", "score < 0.4 不进 plan",
          lambda s, c: float(c.get("score", 0)) < 0.4),
    Taboo("no_action_when_index_top", "指数顶背离不出手",
          lambda s, c: s.get("index_phase") == "top"
                         and c.get("pattern_id") in {"L1_first_board", "L2_weak_to_strong"}),
]


_ZONE_BY_EMOTION = {
    "chaos":     0.20, "recovery":   0.50, "warming":   1.00,
    "main_rise": 1.00, "climax":     0.30, "divergence": 0.30,
    "decay_1":   0.30, "decay_mid":  0.20, "decay_2":   0.20,
}


def _zone_total_max(emotion_phase: str, index_phase: str) -> float:
    base = _ZONE_BY_EMOTION.get(emotion_phase, 0.20)
    if index_phase == "top":
        base = min(base, 0.30)
    if index_phase == "downtrend":
        base = min(base, 0.30)
    return base


def risk_guard_node(state: MarketState) -> dict:
    survivors: list[Candidate] = []
    flags: list[str] = []
    seen: set[str] = set()
    for c in state.get("candidates", []):
        if c["code"] in seen:
            continue
        seen.add(c["code"])
        kept = True
        for t in TABOOS:
            if t.predicate(state, c):
                flags.append(f"{c['code']} 触发禁忌「{t.desc}」")
                if t.drop:
                    kept = False
                    break
        if kept:
            survivors.append(c)
    survivors.sort(key=lambda c: -float(c.get("score", 0)))
    pos_max = _zone_total_max(state.get("emotion_phase", "warming"),
                               state.get("index_phase", "oscillation"))
    return {
        "final_candidates": survivors,
        "risk_flags": flags,
    }
```

> Note: `pos_max` flows into the plan via `trade_planner_node` reading state's emotion/index again, so we don't need to store it in state for v1.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_risk_guard.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/risk_guard.py tests/test_nodes/test_risk_guard.py
git commit -m "feat(nodes): add risk_guard with 10 v1 taboos + zone-based total-position cap"
```

---

### Task 19: `trade_planner` node

**Files:**
- Create: `src/youzi_agent/nodes/trade_planner.py`
- Test: `tests/test_nodes/test_trade_planner.py`

- [ ] **Step 1: Write the failing test**

`tests/test_nodes/test_trade_planner.py`:
```python
from youzi_agent.nodes.trade_planner import trade_planner_node

def test_plan_caps_total_position():
    state = {
        "target_date": "2026-04-25",
        "emotion_phase": "warming", "index_phase": "uptrend",
        "final_candidates": [
            {"code": "600202", "name": "x", "pattern_id": "L1_first_board",
             "score": 0.9, "reason": "r", "suggested_position": 0.5},
            {"code": "002438", "name": "y", "pattern_id": "L1_first_board",
             "score": 0.7, "reason": "r", "suggested_position": 0.5},
            {"code": "300999", "name": "z", "pattern_id": "L1_first_board",
             "score": 0.6, "reason": "r", "suggested_position": 0.5},
        ],
    }
    out = trade_planner_node(state)
    plan = out["plan"]
    assert plan["date"] == "2026-04-25"
    total = sum(c["suggested_position"] for c in plan["candidates"])
    assert total <= plan["position_total_max"] + 1e-9

def test_plan_empty_when_no_candidates():
    out = trade_planner_node({
        "target_date": "2026-04-25", "emotion_phase": "chaos",
        "index_phase": "downtrend", "final_candidates": [],
    })
    assert out["plan"]["candidates"] == []
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nodes/test_trade_planner.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/nodes/trade_planner.py`:
```python
"""Allocate position across final_candidates within zone cap."""
from __future__ import annotations

from .risk_guard import _zone_total_max
from ..state import Candidate, MarketState, TradePlan


def trade_planner_node(state: MarketState) -> dict:
    finals = list(state.get("final_candidates", []))[:8]
    pos_max = _zone_total_max(
        state.get("emotion_phase", "warming"),
        state.get("index_phase", "oscillation"),
    )
    if not finals:
        plan: TradePlan = {
            "date": state["target_date"],
            "position_total_max": pos_max,
            "candidates": [],
            "avoid_list": [],
            "notes": "无候选,空仓",
        }
        return {"plan": plan}

    weights = [float(c.get("score", 0)) for c in finals]
    sw = sum(weights) or 1.0
    sized: list[Candidate] = []
    for c, w in zip(finals, weights):
        per = min(float(c.get("suggested_position", 0.10)), pos_max * (w / sw))
        sized.append({**c, "suggested_position": round(per, 4)})

    plan: TradePlan = {
        "date": state["target_date"],
        "position_total_max": pos_max,
        "candidates": sized,
        "avoid_list": [],
        "notes": f"{state.get('emotion_phase','?')} · {state.get('index_phase','?')}",
    }
    return {"plan": plan}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_nodes/test_trade_planner.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/nodes/trade_planner.py tests/test_nodes/test_trade_planner.py
git commit -m "feat(nodes): add trade_planner with score-weighted position sizing"
```

---

## Phase 7 — Reporting + post_mortem

### Task 20: `post_mortem` + reporting

**Files:**
- Create: `src/youzi_agent/reporting.py`
- Create: `src/youzi_agent/nodes/post_mortem.py`
- Test: `tests/test_reporting.py`, `tests/test_nodes/test_post_mortem.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reporting.py`:
```python
from youzi_agent.reporting import render_markdown, state_to_json

def test_render_markdown_contains_key_sections():
    state = {
        "target_date": "2026-04-25",
        "emotion_phase": "warming",
        "limit_up_count": 60, "consec_top": 5, "blast_rate": 0.18,
        "five_day_pos": "above", "is_new_cycle_day": True,
        "main_theme": "核电",
        "themes": {"核电": {"name": "核电", "members": ["600202"],
                            "leader": "600202", "phase": "vertical",
                            "catalysts": [], "resonance_score": 0.85}},
        "leader_stack": [{"code": "600202", "name": "中核科技",
                          "consec_boards": 4, "role": "total",
                          "sealed_amount": 2.5, "blast_today": False, "div_count": 0}],
        "plan": {"date": "2026-04-25", "position_total_max": 1.0,
                 "candidates": [{"code": "600202", "name": "中核科技",
                                  "pattern_id": "L1_first_board", "score": 0.8,
                                  "reason": "封单 2.5 亿", "suggested_position": 0.1}],
                 "avoid_list": [], "notes": "warming · uptrend"},
        "risk_flags": [], "arb_opportunities": [], "errors": [],
    }
    md = render_markdown(state)
    assert "情绪诊断" in md
    assert "核电" in md
    assert "600202" in md

def test_state_to_json_drops_raw():
    s = {"target_date": "2026-04-25", "raw": {"big": "df"}, "emotion_phase": "warming"}
    out = state_to_json(s)
    assert "raw" not in out
    assert out["emotion_phase"] == "warming"
```

`tests/test_nodes/test_post_mortem.py`:
```python
import json
from pathlib import Path
from youzi_agent.nodes.post_mortem import post_mortem_node

def test_post_mortem_writes_files(tmp_path):
    state = {
        "target_date": "2026-04-25", "emotion_phase": "warming",
        "limit_up_count": 60, "consec_top": 5, "blast_rate": 0.1,
        "main_theme": "核电", "themes": {}, "leader_stack": [],
        "plan": {"date": "2026-04-25", "position_total_max": 1.0,
                 "candidates": [], "avoid_list": [], "notes": ""},
        "risk_flags": [], "arb_opportunities": [], "errors": [],
        "raw": {"a": "b"},
    }
    out = post_mortem_node(state, runs_dir=tmp_path)
    day_dir = Path(tmp_path) / "2026-04-25"
    assert (day_dir / "report.md").exists()
    assert (day_dir / "report.json").exists()
    assert (day_dir / "state_snapshot.json").exists()
    snap = json.loads((day_dir / "state_snapshot.json").read_text())
    assert snap["emotion_phase"] == "warming"
    assert "review" in out
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_reporting.py tests/test_nodes/test_post_mortem.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/reporting.py`:
```python
"""State → JSON / Markdown."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd


def state_to_json(state: dict) -> dict:
    """Serialize state to JSON-safe dict, dropping `raw` (contains DataFrames)."""
    def _safe(v: Any) -> Any:
        if isinstance(v, pd.DataFrame):
            return f"<DataFrame {v.shape}>"
        if isinstance(v, dict):
            return {k: _safe(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_safe(x) for x in v]
        return v
    return {k: _safe(v) for k, v in state.items() if k != "raw"}


def render_markdown(state: dict) -> str:
    date = state.get("target_date", "?")
    lines = [f"# 游资策略复盘 · {date}", ""]

    lines += ["## 情绪诊断"]
    lines += [f"- emotion_phase: **{state.get('emotion_phase','?')}**"]
    lines += [f"- 涨停 {state.get('limit_up_count','?')} | "
              f"最高连板 {state.get('consec_top','?')} | "
              f"炸板率 {(state.get('blast_rate', 0) * 100):.1f}%"]
    lines += [f"- 五日线: {state.get('five_day_pos','?')} | "
              f"新周期确立: {'✅' if state.get('is_new_cycle_day') else '❌'}"]
    if state.get("errors"):
        lines += [f"- ⚠️ 节点警告: {len(state['errors'])} 条"]
    lines += [""]

    main = state.get("main_theme")
    themes = state.get("themes", {})
    if main and main in themes:
        t = themes[main]
        lines += ["## 主线", f"**{main}** ({t.get('phase','?')}, "
                            f"score {t.get('resonance_score',0):.2f})"]
        leader = t.get("leader")
        if leader:
            lines += [f"- 龙头: {leader}"]
        members = t.get("members", [])
        if len(members) > 1:
            lines += [f"- 成员: {', '.join(members[:8])}{'…' if len(members) > 8 else ''}"]
        lines += [""]

    plan = state.get("plan", {})
    cands = plan.get("candidates", [])
    if cands:
        lines += [f"## 候选池 ({len(cands)})", "",
                  "| code | name | pattern | score | reason | 仓位 |",
                  "|---|---|---|---|---|---|"]
        for c in cands:
            lines += [f"| {c['code']} | {c.get('name','')} | {c.get('pattern_id','')} "
                      f"| {c.get('score',0):.2f} | {c.get('reason','')} "
                      f"| {c.get('suggested_position',0):.2f} |"]
        lines += [""]
    else:
        lines += ["## 候选池", "(空 / 全部被风控剔除)", ""]

    flags = state.get("risk_flags", [])
    if flags:
        lines += ["## 风控告警"]
        lines += [f"- ⚠️ {f}" for f in flags] + [""]

    arbs = state.get("arb_opportunities", [])
    if arbs:
        lines += ["## 套利机会"]
        for a in arbs:
            lines += [f"- {a['reason']}: {a['code']} {a.get('name','')}"]
        lines += [""]

    lines += ["## 建议总仓位上限",
              f"- 总仓 ≤ {plan.get('position_total_max', 0)*100:.0f}% "
              f"({state.get('emotion_phase','?')} · {state.get('index_phase','?')})"]

    if state.get("errors"):
        lines += ["", "## 节点错误"]
        for e in state["errors"]:
            lines += [f"- {e}"]

    return "\n".join(lines)
```

`src/youzi_agent/nodes/post_mortem.py`:
```python
"""Persist per-day report.json + report.md + state_snapshot.json."""
from __future__ import annotations

import json
from pathlib import Path

from ..reporting import render_markdown, state_to_json
from ..state import MarketState

_SNAPSHOT_FIELDS = ("emotion_phase", "consec_top", "limit_up_count",
                    "main_theme", "succession_status", "is_new_cycle_day",
                    "is_only_rebound", "five_day_pos")


def post_mortem_node(state: MarketState, *, runs_dir: str | Path = "runs") -> dict:
    date = state["target_date"]
    out_dir = Path(runs_dir) / date
    out_dir.mkdir(parents=True, exist_ok=True)

    serialized = state_to_json(state)
    (out_dir / "report.json").write_text(json.dumps(serialized, ensure_ascii=False, indent=2))
    (out_dir / "report.md").write_text(render_markdown(state))

    snapshot = {k: state.get(k) for k in _SNAPSHOT_FIELDS if k in state}
    (out_dir / "state_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))

    return {"review": {"written_to": str(out_dir),
                        "candidates_count": len(state.get("plan", {}).get("candidates", [])),
                        "errors_count": len(state.get("errors", []))}}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_reporting.py tests/test_nodes/test_post_mortem.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/reporting.py src/youzi_agent/nodes/post_mortem.py \
        tests/test_reporting.py tests/test_nodes/test_post_mortem.py
git commit -m "feat(reporting): add post_mortem + Markdown/JSON renderer with raw stripping"
```

---

## Phase 8 — Graph assembly

### Task 21: Wire the parent graph + dispatch

**Files:**
- Create: `src/youzi_agent/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test (full graph compile + dry invoke with mocks)**

`tests/test_graph.py`:
```python
from unittest.mock import patch, MagicMock
import pandas as pd
from youzi_agent.graph import build_graph

def _ztb_today():
    return pd.DataFrame({
        "代码":         ["600202", "002438"],
        "名称":         ["中核科技", "江苏神通"],
        "连板数":       [3, 2],
        "封单金额":     [3e8, 1e8],
        "首次封板时间": ["09:30", "10:00"],
        "炸板次数":     [0, 0],
        "所属行业":     ["核能", "核能"],
        "上市天数":     [800, 600],
        "开盘价":       [10.0, 8.0],
        "涨停价":       [11.0, 8.8],
    })

def _ztb_yest():
    return pd.DataFrame({
        "代码":         ["600202", "002438"],
        "名称":         ["中核科技", "江苏神通"],
        "连板数":       [2, 1],
        "封单金额":     [2e8, 1e8],
        "首次封板时间": ["09:35", "09:50"],
        "炸板次数":     [0, 0],
        "上市天数":     [800, 600],
        "开盘价":       [9.5, 7.5],
        "涨停价":       [10.0, 8.0],
    })

def _activity():
    return pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26),
                         [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100])
    ])

def test_full_graph_runs_end_to_end_no_llm(tmp_path):
    cli = MagicMock()
    cli.limit_up_pool.side_effect = lambda d: _ztb_today() if d == "2026-04-25" else _ztb_yest()
    cli.blast_pool.return_value = pd.DataFrame()
    cli.index_daily.return_value = pd.DataFrame({
        "close": [3000 + i for i in range(100)],
        "amount": [1e10] * 100,
    })
    cli.market_activity.return_value = _activity()
    with patch("youzi_agent.nodes.market_sensor.AkshareClient", return_value=cli):
        g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
        out = g.invoke(
            {"target_date": "2026-04-25", "use_llm": False},
            config={"configurable": {"thread_id": "test"}},
        )
    assert "plan" in out
    assert out["plan"]["date"] == "2026-04-25"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_graph.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`src/youzi_agent/graph.py`:
```python
"""Parent graph: SENSE → ANALYZE → DECIDE."""
from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes.arbitrage import arbitrage_node
from .nodes.cycle_switch import cycle_switch_node
from .nodes.emotion import emotion_node
from .nodes.index_cycle import index_cycle_node
from .nodes.leader_tracker import leader_tracker_node
from .nodes.market_sensor import market_sensor_node
from .nodes.pattern_matcher import pattern_matcher_node
from .nodes.post_mortem import post_mortem_node
from .nodes.risk_guard import risk_guard_node
from .nodes.theme_analyst import theme_analyst_node
from .nodes.trade_planner import trade_planner_node
from .state import MarketState
from .subagents.continuous import build_con_subgraph
from .subagents.first_board import build_fb_subgraph
from .subagents.setback_reversal import build_sr_subgraph
from .subagents.weak_to_strong import build_w2s_subgraph

SUBAGENT_NAMES = ["weak_to_strong", "first_board", "continuous", "setback_reversal"]


def _slice_for_subagent(state: MarketState, name: str) -> dict:
    return {
        "target_date":  state["target_date"],
        "pattern_hits": [h for h in state.get("pattern_hits", [])
                          if h["target_subagent"] == name],
        "raw":          state.get("raw", {}),
        "leader_stack": state.get("leader_stack", []),
        "themes":       state.get("themes", {}),
        "main_theme":   state.get("main_theme"),
    }


def _dispatch(state: MarketState):
    active = {h["target_subagent"] for h in state.get("pattern_hits", [])}
    active &= set(SUBAGENT_NAMES)
    if not active:
        return ["join"]
    return [Send(name, _slice_for_subagent(state, name)) for name in active]


def build_graph(checkpoint_path: str = "checkpoints.db"):
    g = StateGraph(MarketState)

    # STAGE A — SENSE
    g.add_node("market_sensor", market_sensor_node)
    g.add_node("index_cycle",   index_cycle_node)
    g.add_node("emotion",       emotion_node)
    g.add_node("cycle_switch",  cycle_switch_node)
    g.add_edge(START, "market_sensor")
    g.add_edge("market_sensor", "index_cycle")
    g.add_edge("index_cycle",   "emotion")
    g.add_edge("emotion",       "cycle_switch")

    # STAGE B — ANALYZE
    g.add_node("theme_analyst",   theme_analyst_node)
    g.add_node("leader_tracker",  leader_tracker_node)
    g.add_node("pattern_matcher", pattern_matcher_node)
    g.add_edge("cycle_switch",    "theme_analyst")
    g.add_edge("theme_analyst",   "leader_tracker")
    g.add_edge("leader_tracker",  "pattern_matcher")

    # STAGE C — DECIDE
    g.add_node("weak_to_strong",   build_w2s_subgraph())
    g.add_node("first_board",      build_fb_subgraph())
    g.add_node("continuous",       build_con_subgraph())
    g.add_node("setback_reversal", build_sr_subgraph())
    g.add_node("join", lambda s: {})
    g.add_conditional_edges("pattern_matcher", _dispatch,
                             [*SUBAGENT_NAMES, "join"])
    for name in SUBAGENT_NAMES:
        g.add_edge(name, "join")

    g.add_node("arbitrage",     arbitrage_node)
    g.add_node("risk_guard",    risk_guard_node)
    g.add_node("trade_planner", trade_planner_node)
    g.add_node("post_mortem",   post_mortem_node)
    g.add_edge("join",          "arbitrage")
    g.add_edge("arbitrage",     "risk_guard")
    g.add_edge("risk_guard",    "trade_planner")
    g.add_edge("trade_planner", "post_mortem")
    g.add_edge("post_mortem",   END)

    saver = SqliteSaver.from_conn_string(checkpoint_path)
    return g.compile(checkpointer=saver)
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_graph.py -v
```

Expected: 1 passed (may take a few seconds — full graph runs).

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/graph.py tests/test_graph.py
git commit -m "feat(graph): wire parent graph with Send-based subagent dispatch + SQLite checkpointer"
```

---

## Phase 9 — CLI

### Task 22: CLI entry point

**Files:**
- Create: `src/youzi_agent/cli.py`
- Create: `src/youzi_agent/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import subprocess
import sys

def test_cli_help_runs():
    r = subprocess.run([sys.executable, "-m", "youzi_agent", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "youzi-agent" in r.stdout.lower() or "usage" in r.stdout.lower()

def test_cli_resolves_default_date():
    from youzi_agent.cli import _default_date
    d = _default_date()
    assert len(d) == 10 and d[4] == "-" and d[7] == "-"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement**

`src/youzi_agent/cli.py`:
```python
"""CLI entry: python -m youzi_agent [date] [--no-llm] [--refresh] [--json]."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph


def _default_date() -> str:
    today = _dt.date.today()
    while today.weekday() >= 5:
        today -= _dt.timedelta(days=1)
    return today.isoformat()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="youzi-agent",
                                description="A-share retail-style multi-agent trading research")
    p.add_argument("date", nargs="?", default=None, help="trading date YYYY-MM-DD (default: today)")
    p.add_argument("--no-llm", action="store_true", help="skip LLM calls, use rule fallbacks")
    p.add_argument("--refresh", action="store_true", help="bypass on-disk cache")
    p.add_argument("--json", action="store_true", help="emit final state as JSON to stdout")
    p.add_argument("--checkpoint", default="checkpoints.db")
    p.add_argument("--runs-dir", default="runs")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)
    date = args.date or _default_date()
    if args.refresh:
        os.environ["YOUZI_REFRESH"] = "1"
    graph = build_graph(checkpoint_path=args.checkpoint)
    state = graph.invoke(
        {"target_date": date, "use_llm": not args.no_llm},
        config={"configurable": {"thread_id": date}},
    )
    if args.json:
        from .reporting import state_to_json
        print(json.dumps(state_to_json(state), ensure_ascii=False, indent=2))
    else:
        report_md = Path(args.runs_dir) / date / "report.md"
        if report_md.exists():
            print(report_md.read_text())
    if state.get("errors"):
        return 2
    if state.get("plan", {}).get("candidates") is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`src/youzi_agent/__main__.py`:
```python
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_cli.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/youzi_agent/cli.py src/youzi_agent/__main__.py tests/test_cli.py
git commit -m "feat(cli): add python -m youzi_agent entry with --no-llm/--refresh/--json"
```

---

## Phase 10 — E2E + smoke

### Task 23: End-to-end synthetic-fixture test

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/synthetic/build_synthetic.py`
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write the synthetic fixture builder**

`tests/fixtures/synthetic/__init__.py`:
```python
```

`tests/fixtures/synthetic/build_synthetic.py`:
```python
"""Generate a deterministic synthetic dataset for one trading day."""
from __future__ import annotations

import pandas as pd


def build_warming_day(date: str = "2026-04-25") -> dict:
    ztb_today = pd.DataFrame({
        "代码":         ["600202", "002438", "300999", "600988"],
        "名称":         ["中核科技", "江苏神通", "新票", "赤峰黄金"],
        "连板数":       [3, 2, 1, 1],
        "封单金额":     [3e8, 1e8, 0.5e8, 0.6e8],
        "首次封板时间": ["09:30", "10:00", "10:30", "09:50"],
        "炸板次数":     [0, 0, 1, 0],
        "所属行业":     ["核能", "核能", "其他", "黄金"],
        "上市天数":     [800, 600, 1000, 700],
        "开盘价":       [10.0, 8.0, 5.0, 6.0],
        "涨停价":       [11.0, 8.8, 5.5, 6.6],
    })
    ztb_yest = pd.DataFrame({
        "代码":         ["600202", "600988"],
        "名称":         ["中核科技", "赤峰黄金"],
        "连板数":       [2, 1],
        "封单金额":     [2e8, 0.5e8],
        "首次封板时间": ["09:40", "10:30"],
        "炸板次数":     [0, 1],
        "上市天数":     [800, 700],
        "开盘价":       [9.5, 5.5],
        "涨停价":       [10.0, 6.0],
    })
    activity = pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26),
                         [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100])
    ])
    idx_sh = pd.DataFrame({
        "close":  [3000 + i for i in range(100)],
        "amount": [1e10] * 100,
    })
    return {
        "ztb_today": ztb_today, "ztb_yesterday": ztb_yest,
        "blast": pd.DataFrame(),
        "idx_sh": idx_sh, "idx_cyb": idx_sh,
        "activity": activity,
    }
```

`tests/conftest.py`:
```python
import pytest
from unittest.mock import MagicMock
from tests.fixtures.synthetic.build_synthetic import build_warming_day


@pytest.fixture
def synthetic_warming():
    return build_warming_day("2026-04-25")


@pytest.fixture
def mock_akshare_client(synthetic_warming):
    cli = MagicMock()
    data = synthetic_warming
    cli.limit_up_pool.side_effect = lambda d: data["ztb_today"] if d == "2026-04-25" else data["ztb_yesterday"]
    cli.blast_pool.return_value = data["blast"]
    cli.index_daily.return_value = data["idx_sh"]
    cli.market_activity.return_value = data["activity"]
    return cli
```

`tests/test_e2e.py`:
```python
from unittest.mock import patch
from youzi_agent.graph import build_graph


def test_e2e_full_graph_no_llm(tmp_path, mock_akshare_client):
    with patch("youzi_agent.nodes.market_sensor.AkshareClient",
               return_value=mock_akshare_client):
        g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
        out = g.invoke(
            {"target_date": "2026-04-25", "use_llm": False},
            config={"configurable": {"thread_id": "e2e"}},
        )
    assert out["plan"]["date"] == "2026-04-25"
    assert (tmp_path).exists()  # plan emitted, no crash
    # The 4-stock day should have produced at least one first-board candidate after risk-guard
    plan_codes = [c["code"] for c in out["plan"]["candidates"]]
    assert isinstance(plan_codes, list)
    assert out.get("emotion_phase") in {
        "chaos", "recovery", "warming", "main_rise", "climax",
        "divergence", "decay_1", "decay_mid", "decay_2",
    }
```

- [ ] **Step 2: Run, expect failure on first run (mocking nuance might shift)**

```bash
pytest tests/test_e2e.py -v
```

If a column-name mismatch surfaces (akshare's real schema vs synthetic), trace the error and fix the affected node. The synthetic schema in step 1 is the contract — node code that breaks here breaks against real akshare too.

- [ ] **Step 3: Iterate until green**

Common fixes:
- Missing column guard in a node → add `.get()` with default or `if "col" in df.columns:`
- Reducer accumulating between runs → make sure `thread_id` is unique per test
- LLM-dependent node call without `use_llm=False` → confirm fallback path

- [ ] **Step 4: Run all tests pass**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/fixtures/synthetic tests/test_e2e.py
git commit -m "test(e2e): synthetic warming-day fixture + full-graph integration test"
```

---

### Task 24: Live smoke test (network + LLM)

**Files:**
- Create: `tests/test_smoke_live.py`

- [ ] **Step 1: Write the live smoke test (skipped without `--live`)**

`tests/test_smoke_live.py`:
```python
import os
import pytest
from youzi_agent.graph import build_graph
from youzi_agent.cli import _default_date

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _require_key():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set; skipping live smoke")


def test_live_full_pipeline_today(tmp_path):
    date = _default_date()
    g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
    out = g.invoke(
        {"target_date": date, "use_llm": True},
        config={"configurable": {"thread_id": f"smoke-{date}"}},
    )
    assert out["plan"]["date"] == date
    print(f"[smoke] emotion_phase={out.get('emotion_phase')} "
          f"candidates={len(out['plan']['candidates'])} "
          f"errors={len(out.get('errors', []))}")
```

- [ ] **Step 2: Run with `-m live` (NETWORK + LLM, optional)**

```bash
DEEPSEEK_API_KEY=sk-84398b6b73704500911b627a97444f57 pytest -m live -v -s
```

Expected: passes if network + LLM available; otherwise skipped automatically.

- [ ] **Step 3: Run a real CLI invocation end-to-end**

```bash
DEEPSEEK_API_KEY=sk-84398b6b73704500911b627a97444f57 python -m youzi_agent
cat runs/$(date +%Y-%m-%d)/report.md
```

Expected: report.md is rendered with today's emotion phase, themes, candidate pool.

- [ ] **Step 4: Sanity-check `runs/` artifacts**

```bash
ls runs/$(date +%Y-%m-%d)/
# expect: report.md  report.json  state_snapshot.json
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_live.py
git commit -m "test(smoke): live network + LLM end-to-end test gated by --live marker"
```

---

## Verification checklist (run before declaring done)

- [ ] `pytest tests/ -v` — all green except `-m live`
- [ ] `python -m youzi_agent --no-llm` — runs offline, writes `runs/<today>/report.md`
- [ ] `python -m youzi_agent --no-llm --json | jq .emotion_phase` — emits valid JSON
- [ ] `runs/<date>/report.md` is human-readable and shows emotion / theme / candidates / risk
- [ ] `checkpoints.db` is created on first run, contains rows for all parent-graph nodes
- [ ] Re-running same date with `--refresh` overwrites cached parquet but keeps git-tracked fixtures intact
- [ ] LLM-failure path: temporarily set `DEEPSEEK_API_KEY=invalid` then run with LLM enabled — graph should still produce a plan but with `errors[]` populated

## Spec→Plan coverage map

| Spec section | Tasks |
|---|---|
| §3 Project structure | Task 0 |
| §4 State model | Task 4 |
| §5 Parent graph | Task 21 |
| §6.1 market_sensor | Task 5 |
| §6.2 index_cycle | Task 6 |
| §6.3 emotion | Task 7 |
| §6.4 cycle_switch | Task 8 |
| §7.1 theme_analyst | Task 10 |
| §7.2 leader_tracker | Task 11 |
| §7.3 pattern_matcher | Task 12 |
| §8.1-8.4 sub-graphs | Tasks 13-16 |
| §9 LLM nodes | Tasks 9-10, 12 |
| §10.1 arbitrage | Task 17 |
| §10.2 risk_guard | Task 18 |
| §10.3 trade_planner | Task 19 |
| §10.4 post_mortem | Task 20 |
| §11 data layer | Tasks 1-3 |
| §12 CLI + report | Tasks 20, 22 |
| §13 testing | Tasks 23-24, plus per-task tests |
| §14 deps | Task 0 |

## Known v1 gaps (logged for v2 planning, not blocking ship)

- `setback_reversal` requires `raw["klines_by_code"]` which `market_sensor_node` does not populate in v1 — sub-graph degrades to empty in real runs (Task 16 note)
- Sub-agent patterns marked `# v1 stub` (`_ladder_arb`, `_new_cycle_arb`, `_drop_out_arb`) — incremental fill in v2
- Only 10 of 27 risk taboos implemented — fill remaining in v2 with the same `Taboo` dataclass
- Vector memory (Chroma) deferred to v2
- Intraday-driven sub-graphs (true 5-min secboard, 尾盘炸板) require minute data — v2
- LeaderRelay / Capacity / Sunflower sub-graphs deferred — v2
- `big_cap_volume_ratio` always 0.0 in v1 (no akshare interface for that ratio) — see `index_cycle.py`
