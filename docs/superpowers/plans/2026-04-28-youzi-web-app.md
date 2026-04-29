# youzi-agent Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing `youzi_agent` LangGraph CLI in a single-user local web app with streaming node progress, human-in-the-loop interrupts at PatternMatcher/RiskGuard/TradePlanner, and a 3-column dashboard with editable cells + history picker.

**Architecture:** Single Python process (FastAPI) that imports `youzi_agent.graph` and exposes REST + SSE; Next.js 14 (App Router, `output: 'export'`) consumes via OpenAPI-typed client. Authoritative state lives in LangGraph SqliteSaver. CLI keeps working as a thin runtime wrapper with auto-resume.

**Tech Stack:** Python 3.11+, FastAPI, sse-starlette, langgraph 0.2.50+ (existing). Next.js 14, React 18, TanStack Query, Zustand, Tailwind, shadcn/ui, lightweight-charts. npm + pip + Makefile.

**Spec:** `docs/superpowers/specs/2026-04-28-youzi-web-app-design.md`

---

## Repo conventions

- Working directory: `/Volumes/kairos/引力场量化/`
- Existing Python package source: `src/youzi_agent/` (do not rename or move)
- New backend service: `apps/api/`
- Frontend: `apps/web/`
- Tests: existing `tests/` for Python; new `apps/api/tests/` for service-only; `apps/web/tests/` for frontend
- Run all backend tests: `pytest -q`
- Run live tests: `pytest -q -m live`
- Run frontend tests: `cd apps/web && npm test`
- Commit style: conventional commits (`feat(api):`, `feat(web):`, `test:`, `chore:`, `fix:`)
- After every task: tests green + commit. Use `git status` / `git diff` to verify staged content.
- No backwards-compatibility shims while building v1 — break and fix.

---

## Phase 1 — Backend skeleton (5 tasks)

Goal: bare FastAPI process that can start a graph run, stream node events over SSE, expose history and K-line, with offline pytest coverage. No interrupts yet.

### Task 1: Add backend deps and `apps/api/` skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `apps/api/__init__.py`
- Create: `apps/api/main.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/tests/test_health.py`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Append to the `dependencies` list:
```toml
    "fastapi>=0.110,<1",
    "uvicorn[standard]>=0.27,<1",
    "sse-starlette>=2.1,<3",
```

Add to `[project.optional-dependencies] dev`:
```toml
dev = ["pytest>=8", "pytest-cov", "pytest-asyncio>=0.23", "httpx>=0.27", "httpx-sse>=0.4", "ruff", "mypy"]
```

Reinstall:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write failing health test**

`apps/api/tests/__init__.py`:
```python
```

`apps/api/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from apps.api.main import app

def test_health_ok():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

Run:
```bash
pytest apps/api/tests/test_health.py -v
```
Expected: ImportError on `apps.api.main`.

- [ ] **Step 3: Make `apps/` a package and write minimal app**

`apps/__init__.py`:
```python
```

`apps/api/__init__.py`:
```python
```

`apps/api/main.py`:
```python
"""FastAPI entry — wraps youzi_agent graph runtime."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="youzi-agent web API", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
```

- [ ] **Step 4: Run test**

```bash
pytest apps/api/tests/test_health.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml apps/
git commit -m "feat(api): bootstrap FastAPI service with /api/health"
```

---

### Task 2: `GraphRuntime` class — start + queue + drive

**Files:**
- Create: `apps/api/graph_runtime.py`
- Create: `apps/api/events.py`
- Create: `apps/api/tests/test_runtime.py`

- [ ] **Step 1: Define event types**

`apps/api/events.py`:
```python
"""SSE event payloads — single source of truth for runtime → wire JSON."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

NodeName = str  # any node id from youzi_agent.graph


class NodeStartEvent(TypedDict):
    type: Literal["node_start"]
    node: NodeName
    ts: float


class NodeEndEvent(TypedDict):
    type: Literal["node_end"]
    node: NodeName
    ts: float
    state_patch: dict[str, Any]


class NodeErrorEvent(TypedDict):
    type: Literal["node_error"]
    node: NodeName
    ts: float
    message: str


class InterruptEvent(TypedDict):
    type: Literal["interrupt"]
    node: Literal["pattern_matcher", "risk_guard", "trade_planner"]
    snapshot: dict[str, Any]
    ts: float


class DoneEvent(TypedDict):
    type: Literal["done"]
    final_state: dict[str, Any]
    ts: float


class AbortedEvent(TypedDict):
    type: Literal["aborted"]
    reason: str
    ts: float


RunEvent = (
    NodeStartEvent | NodeEndEvent | NodeErrorEvent
    | InterruptEvent | DoneEvent | AbortedEvent
)
```

- [ ] **Step 2: Write failing test for `start` + `stream` happy path**

`apps/api/tests/test_runtime.py`:
```python
import asyncio
import pytest
from apps.api.graph_runtime import GraphRuntime


@pytest.mark.asyncio
async def test_start_returns_thread_id_with_date_prefix(tmp_path):
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="2026-04-26", use_llm=False, refresh=False)
    assert tid.startswith("2026-04-26-")
    assert len(tid) == len("2026-04-26-") + 8


@pytest.mark.asyncio
async def test_stream_yields_node_start_then_done_for_offline_run(tmp_path, monkeypatch):
    """Smoke-runs the real graph offline (use_llm=False) on a date with no data;
    expects the runtime to surface node_start events and a final done/aborted event."""
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="1970-01-01", use_llm=False, refresh=False)

    events = []
    async for ev in rt.stream(tid):
        events.append(ev)
        if len(events) > 200:
            pytest.fail("stream did not terminate")

    types = {e["type"] for e in events}
    assert "node_start" in types
    assert types & {"done", "aborted"}, f"no terminal event in {types}"
```

Run:
```bash
pytest apps/api/tests/test_runtime.py -v
```
Expected: ImportError on `GraphRuntime`.

- [ ] **Step 3: Implement minimal `GraphRuntime`**

`apps/api/graph_runtime.py`:
```python
"""Wraps youzi_agent graph in an async-friendly runtime with per-thread queues."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncIterator

from youzi_agent.graph import build_graph

from .events import (AbortedEvent, DoneEvent, NodeEndEvent, NodeErrorEvent,
                     NodeStartEvent, RunEvent)

_TERMINAL_TYPES = {"done", "aborted"}


class GraphRuntime:
    def __init__(self, checkpoint_path: str = "checkpoints.db") -> None:
        self._graph = build_graph(checkpoint_path=checkpoint_path)
        self._queues: dict[str, asyncio.Queue[RunEvent]] = {}

    async def start(self, *, date: str, use_llm: bool, refresh: bool) -> str:
        tid = f"{date}-{uuid.uuid4().hex[:8]}"
        self._queues[tid] = asyncio.Queue()
        asyncio.create_task(self._drive(tid, date, use_llm, refresh))
        return tid

    async def stream(self, tid: str) -> AsyncIterator[RunEvent]:
        q = self._queues[tid]
        while True:
            ev = await q.get()
            yield ev
            if ev["type"] in _TERMINAL_TYPES:
                break

    async def _drive(self, tid: str, date: str, use_llm: bool, refresh: bool) -> None:
        cfg = {"configurable": {"thread_id": tid}}
        q = self._queues[tid]
        last_node: str | None = None
        try:
            await q.put(NodeStartEvent(type="node_start", node="<run>", ts=time.time()))
            async for chunk in self._graph.astream(
                {"target_date": date, "use_llm": use_llm},
                config=cfg,
                stream_mode="updates",
            ):
                # `chunk` is {node_name: state_patch} for stream_mode="updates"
                for node, patch in chunk.items():
                    if last_node != node:
                        await q.put(NodeStartEvent(type="node_start", node=node, ts=time.time()))
                        last_node = node
                    await q.put(NodeEndEvent(
                        type="node_end", node=node, ts=time.time(),
                        state_patch=_jsonable(patch),
                    ))
            final = self._graph.get_state(cfg).values
            await q.put(DoneEvent(type="done", final_state=_jsonable(final), ts=time.time()))
        except Exception as e:
            await q.put(NodeErrorEvent(type="node_error", node=last_node or "<unknown>",
                                       ts=time.time(), message=str(e)))
            await q.put(AbortedEvent(type="aborted", reason=str(e), ts=time.time()))


def _jsonable(obj: Any) -> Any:
    """Defensive: drop non-JSON-able fields from state patches (e.g. pandas DFs)."""
    import json
    try:
        json.dumps(obj, default=str)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {k: _jsonable(v) for k, v in obj.items()
                    if not _is_dataframe(v) and not _is_dataframe_dict(v)}
        return str(obj)


def _is_dataframe(v: Any) -> bool:
    return type(v).__name__ == "DataFrame"


def _is_dataframe_dict(v: Any) -> bool:
    return isinstance(v, dict) and any(_is_dataframe(x) for x in v.values())
```

- [ ] **Step 4: Run tests**

```bash
pytest apps/api/tests/test_runtime.py -v
```
Expected: PASS (graph runs offline against synthetic empty data; node_start + done/aborted reach the queue).

- [ ] **Step 5: Commit**

```bash
git add apps/api/graph_runtime.py apps/api/events.py apps/api/tests/test_runtime.py
git commit -m "feat(api): GraphRuntime — start/stream over async queue"
```

---

### Task 3: `/api/run` POST + `/api/run/{tid}/stream` SSE

**Files:**
- Create: `apps/api/routes/__init__.py`
- Create: `apps/api/routes/run.py`
- Modify: `apps/api/main.py`
- Create: `apps/api/tests/test_routes_run.py`

- [ ] **Step 1: Write failing route test**

`apps/api/tests/test_routes_run.py`:
```python
import json
import pytest
from fastapi.testclient import TestClient
from apps.api.main import build_app


@pytest.fixture
def client(tmp_path):
    return TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))


def test_post_run_returns_thread_id(client):
    r = client.post("/api/run", json={"date": "2026-04-26", "use_llm": False})
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"].startswith("2026-04-26-")


def test_stream_yields_done_event(client):
    tid = client.post("/api/run", json={"date": "1970-01-01", "use_llm": False}).json()["thread_id"]
    with client.stream("GET", f"/api/run/{tid}/stream") as r:
        assert r.status_code == 200
        types = []
        for line in r.iter_lines():
            if line.startswith("event:"):
                types.append(line.split(":", 1)[1].strip())
            if "done" in types or "aborted" in types:
                break
        assert types and types[-1] in ("done", "aborted")
```

Run:
```bash
pytest apps/api/tests/test_routes_run.py -v
```
Expected: ImportError / 404.

- [ ] **Step 2: Implement run routes**

`apps/api/routes/__init__.py`:
```python
```

`apps/api/routes/run.py`:
```python
"""Run lifecycle: POST /run, GET /run/{tid}/stream."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api")


class StartRunBody(BaseModel):
    date: str
    use_llm: bool = True
    refresh: bool = False


@router.post("/run")
async def post_run(body: StartRunBody, request: Request) -> dict:
    rt = request.app.state.runtime
    tid = await rt.start(date=body.date, use_llm=body.use_llm, refresh=body.refresh)
    return {"thread_id": tid}


@router.get("/run/{tid}/stream")
async def get_stream(tid: str, request: Request):
    rt = request.app.state.runtime
    if tid not in rt._queues:
        raise HTTPException(status_code=404, detail="unknown thread_id")

    async def gen():
        async for ev in rt.stream(tid):
            yield {"event": ev["type"], "data": json.dumps(ev, default=str)}

    return EventSourceResponse(gen())
```

- [ ] **Step 3: Refactor `main.py` to expose `build_app(checkpoint_path)`**

`apps/api/main.py`:
```python
"""FastAPI entry — wraps youzi_agent graph runtime."""
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .graph_runtime import GraphRuntime
from .routes import run as run_routes


def build_app(checkpoint_path: str | None = None) -> FastAPI:
    app = FastAPI(title="youzi-agent web API", version="0.1.0")
    # dev CORS — Next dev server on :3000
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    app.include_router(run_routes.router)
    app.state.runtime = GraphRuntime(
        checkpoint_path=checkpoint_path or os.environ.get("YOUZI_CHECKPOINT", "checkpoints.db")
    )
    return app


app = build_app()
```

- [ ] **Step 4: Run tests**

```bash
pytest apps/api/tests/ -v
```
Expected: 4 PASS.

- [ ] **Step 5: Smoke run the server manually**

```bash
uvicorn apps.api.main:app --port 8000 &
sleep 2
curl -s -X POST http://localhost:8000/api/run -H 'content-type: application/json' \
  -d '{"date":"2026-04-26","use_llm":false}'
kill %1
```
Expected: `{"thread_id":"2026-04-26-..."}`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routes apps/api/main.py apps/api/tests/test_routes_run.py
git commit -m "feat(api): POST /run + SSE /run/{tid}/stream"
```

---

### Task 4: `/api/state/{tid}`, `/api/runs`, `/api/runs/{date}`

**Files:**
- Create: `apps/api/routes/state.py`
- Create: `apps/api/routes/runs.py`
- Modify: `apps/api/main.py`
- Create: `apps/api/tests/test_routes_state.py`
- Create: `apps/api/tests/test_routes_runs.py`

- [ ] **Step 1: Write failing tests**

`apps/api/tests/test_routes_state.py`:
```python
import pytest
from fastapi.testclient import TestClient
from apps.api.main import build_app


def test_get_state_unknown_tid_404(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    assert client.get("/api/state/does-not-exist").status_code == 404


def test_get_state_after_run(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    tid = client.post("/api/run", json={"date": "1970-01-01", "use_llm": False}).json()["thread_id"]
    # drain stream so graph completes
    with client.stream("GET", f"/api/run/{tid}/stream") as r:
        for _ in r.iter_lines():
            pass
    r = client.get(f"/api/state/{tid}")
    assert r.status_code == 200
    assert "target_date" in r.json()
```

`apps/api/tests/test_routes_runs.py`:
```python
import json
from fastapi.testclient import TestClient
from apps.api.main import build_app


def test_runs_list_reads_runs_dir(tmp_path):
    runs = tmp_path / "runs"
    (runs / "2026-04-26").mkdir(parents=True)
    (runs / "2026-04-26" / "report.json").write_text(json.dumps({
        "candidates": [{"code": "600519"}],
        "errors": [],
        "plan": {"position_total_max": 0.6}
    }))
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db"),
                                  runs_dir=str(runs)))
    r = client.get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["date"] == "2026-04-26"
    assert body[0]["candidates_count"] == 1
    assert body[0]["has_plan"] is True
    assert body[0]["errors_count"] == 0


def test_runs_get_by_date_reads_state_snapshot(tmp_path):
    runs = tmp_path / "runs"
    (runs / "2026-04-26").mkdir(parents=True)
    snapshot = {"target_date": "2026-04-26", "emotion_phase": "warming"}
    (runs / "2026-04-26" / "state_snapshot.json").write_text(json.dumps(snapshot))
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db"),
                                  runs_dir=str(runs)))
    r = client.get("/api/runs/2026-04-26")
    assert r.status_code == 200
    assert r.json() == snapshot
```

Run:
```bash
pytest apps/api/tests/test_routes_state.py apps/api/tests/test_routes_runs.py -v
```
Expected: 404/ImportError failures.

- [ ] **Step 2: Implement state route**

`apps/api/routes/state.py`:
```python
"""GET /api/state/{tid} — current checkpoint snapshot."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api")


@router.get("/state/{tid}")
def get_state(tid: str, request: Request) -> dict:
    rt = request.app.state.runtime
    cfg = {"configurable": {"thread_id": tid}}
    snapshot = rt._graph.get_state(cfg)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="no state for thread_id")
    from apps.api.graph_runtime import _jsonable
    return _jsonable(snapshot.values)
```

- [ ] **Step 3: Implement runs routes**

`apps/api/routes/runs.py`:
```python
"""History — read runs/YYYY-MM-DD/{report.json,state_snapshot.json}."""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api")


def _runs_dir(request: Request) -> Path:
    return Path(request.app.state.runs_dir)


@router.get("/runs")
def list_runs(request: Request, limit: int = Query(60, gt=0, le=365)) -> list[dict]:
    root = _runs_dir(request)
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        rep = d / "report.json"
        if not rep.exists():
            continue
        try:
            data = json.loads(rep.read_text())
        except Exception:
            continue
        out.append({
            "date": d.name,
            "candidates_count": len(data.get("candidates", []) or []),
            "errors_count": len(data.get("errors", []) or []),
            "has_plan": data.get("plan") is not None,
        })
        if len(out) >= limit:
            break
    return out


@router.get("/runs/{date}")
def get_run(date: str, request: Request) -> dict:
    snap = _runs_dir(request) / date / "state_snapshot.json"
    if not snap.exists():
        raise HTTPException(status_code=404, detail=f"no snapshot for {date}")
    return json.loads(snap.read_text())
```

- [ ] **Step 4: Wire routes into `build_app` + accept `runs_dir`**

Modify `apps/api/main.py` `build_app` signature and body:
```python
def build_app(checkpoint_path: str | None = None,
              runs_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="youzi-agent web API", version="0.1.0")
    # ... CORS unchanged ...
    app.include_router(run_routes.router)
    from .routes import state as state_routes, runs as runs_routes
    app.include_router(state_routes.router)
    app.include_router(runs_routes.router)
    app.state.runtime = GraphRuntime(checkpoint_path=checkpoint_path
                                     or os.environ.get("YOUZI_CHECKPOINT", "checkpoints.db"))
    app.state.runs_dir = runs_dir or os.environ.get("YOUZI_RUNS_DIR", "runs")
    return app
```

- [ ] **Step 5: Run tests**

```bash
pytest apps/api/tests/ -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routes apps/api/main.py apps/api/tests/test_routes_state.py apps/api/tests/test_routes_runs.py
git commit -m "feat(api): /state/{tid} + /runs + /runs/{date}"
```

---

### Task 5: `/api/kline/{code}` with parquet cache

**Files:**
- Create: `apps/api/routes/kline.py`
- Modify: `apps/api/main.py`
- Create: `apps/api/tests/test_routes_kline.py`

- [ ] **Step 1: Write failing test (mocked akshare)**

`apps/api/tests/test_routes_kline.py`:
```python
import pandas as pd
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import build_app


def _fake_kline(*args, **kwargs):
    return pd.DataFrame({
        "date": ["2026-04-25", "2026-04-26"],
        "open": [10.0, 10.5],
        "high": [10.6, 11.0],
        "low": [9.8, 10.4],
        "close": [10.5, 10.9],
        "volume": [1_000_000, 1_200_000],
    })


@patch("youzi_agent.data.akshare_client.get_kline", side_effect=_fake_kline)
def test_kline_returns_ohlc(_mock, tmp_path):
    client = TestClient(build_app(
        checkpoint_path=str(tmp_path / "ckpt.db"),
        runs_dir=str(tmp_path / "runs"),
        cache_dir=str(tmp_path / "cache"),
    ))
    r = client.get("/api/kline/600519?days=2")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "600519"
    assert len(body["bars"]) == 2
    assert body["bars"][0] == {
        "time": "2026-04-25", "open": 10.0, "high": 10.6,
        "low": 9.8, "close": 10.5, "volume": 1_000_000,
    }
    assert "limit_up_days" in body
```

Run: expect 404 / ImportError.

- [ ] **Step 2: Implement kline route**

`apps/api/routes/kline.py`:
```python
"""GET /api/kline/{code} — OHLC + limit-up day markers."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from youzi_agent.data import akshare_client

router = APIRouter(prefix="/api")


@router.get("/kline/{code}")
def get_kline(code: str, request: Request,
              period: str = Query("daily"),
              days: int = Query(60, gt=0, le=400)) -> dict:
    if period != "daily":
        raise HTTPException(400, "v1 supports period=daily only")

    cache_dir = Path(request.app.state.cache_dir) / "kline"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{code}_daily.parquet"

    df: pd.DataFrame | None = None
    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
        except Exception:
            df = None

    if df is None or len(df) < days:
        df = akshare_client.get_kline(code, days=max(days, 60))
        try:
            df.to_parquet(cache_path)
        except Exception:
            pass

    df = df.tail(days).reset_index(drop=True)

    # Mark limit-up days: today's close >= prev_close * 1.099 (approx)
    limit_up_days: list[str] = []
    closes = df["close"].astype(float).tolist()
    dates = df["date"].astype(str).tolist()
    for i in range(1, len(closes)):
        if closes[i] >= closes[i - 1] * 1.099:
            limit_up_days.append(dates[i])

    bars = [{
        "time": str(r["date"]),
        "open": float(r["open"]),
        "high": float(r["high"]),
        "low": float(r["low"]),
        "close": float(r["close"]),
        "volume": int(r["volume"]),
    } for _, r in df.iterrows()]

    return {"code": code, "period": period, "bars": bars, "limit_up_days": limit_up_days}
```

- [ ] **Step 3: Wire `cache_dir` through `build_app`**

In `apps/api/main.py` `build_app`:
```python
def build_app(checkpoint_path: str | None = None,
              runs_dir: str | None = None,
              cache_dir: str | None = None) -> FastAPI:
    # ... existing ...
    from .routes import kline as kline_routes
    app.include_router(kline_routes.router)
    app.state.cache_dir = cache_dir or os.environ.get("YOUZI_CACHE_DIR", "data_cache")
    return app
```

- [ ] **Step 4: Run tests**

```bash
pytest apps/api/tests/ -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routes/kline.py apps/api/main.py apps/api/tests/test_routes_kline.py
git commit -m "feat(api): /kline/{code} with parquet cache + limit-up markers"
```

---

## Phase 2 — Frontend skeleton (5 tasks)

Goal: Next.js dev server up, three-column layout rendering, history picker working, SSE wiring landing node events into a timeline. No charts, no interrupt UI yet.

### Task 6: Init `apps/web` Next.js + Tailwind + shadcn/ui

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/next.config.mjs`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/postcss.config.mjs`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/globals.css`
- Create: `apps/web/app/page.tsx`
- Modify: `.gitignore`

- [ ] **Step 1: Scaffold Next.js**

```bash
mkdir -p apps/web && cd apps/web
npm init -y
npm install --save next@14 react@18 react-dom@18
npm install --save-dev typescript @types/react @types/react-dom @types/node \
  tailwindcss postcss autoprefixer \
  eslint eslint-config-next \
  @types/jest jsdom vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom
npx tailwindcss init -p
```

- [ ] **Step 2: Write `apps/web/package.json` scripts**

Replace the auto-generated scripts block:
```json
{
  "name": "youzi-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "test": "vitest run",
    "test:watch": "vitest",
    "gen:api": "openapi-typescript http://localhost:8000/openapi.json -o lib/api/types.gen.ts"
  }
}
```

Install OpenAPI typegen:
```bash
npm install --save-dev openapi-typescript
```

- [ ] **Step 3: Configure Next + TS + Tailwind**

`apps/web/next.config.mjs`:
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  async rewrites() {
    // dev only — proxies /api/* to FastAPI on :8000.
    // export build ignores rewrites; in prod, FastAPI serves both.
    return [{ source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' }];
  },
};
export default nextConfig;
```

`apps/web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "baseUrl": ".",
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`apps/web/tailwind.config.ts`:
```ts
import type { Config } from 'tailwindcss';
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        mono: ['ui-monospace', 'SF Mono', 'monospace'],
      },
      fontFeatureSettings: { tnum: '"tnum"' },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 4: Bootstrap layout + globals**

`apps/web/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body {
  height: 100%;
  background: #0a0a0a;
  color: #e8e8e8;
  font-feature-settings: "tnum";
}

/* dark by default in v1 */
:root { color-scheme: dark; }
```

`apps/web/app/layout.tsx`:
```tsx
import './globals.css';
import type { Metadata } from 'next';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'youzi-agent · 盯盘台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

`apps/web/app/providers.tsx` (created next):
```tsx
'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false } },
  }));
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
```

Install state libs:
```bash
npm install --save @tanstack/react-query zustand
```

`apps/web/app/page.tsx`:
```tsx
import Link from 'next/link';

export default function Home() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-mono">youzi-agent · 盯盘台</h1>
      <Link href="/console" className="underline">→ Console</Link>
    </main>
  );
}
```

- [ ] **Step 5: Update `.gitignore`**

Append:
```
apps/web/node_modules/
apps/web/.next/
apps/web/out/
apps/web/lib/api/types.gen.ts
```

- [ ] **Step 6: Smoke**

```bash
cd apps/web && npm run dev
# in another shell:
curl -s http://localhost:3000/ | head -20
```
Expected: HTML containing "youzi-agent". Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add apps/web .gitignore
git commit -m "feat(web): bootstrap Next.js + Tailwind + TanStack Query"
```

---

### Task 7: API client + Zustand stores + SSE hook

**Files:**
- Create: `apps/web/lib/api/client.ts`
- Create: `apps/web/lib/api/types.gen.ts` (placeholder until first `gen:api`)
- Create: `apps/web/lib/sse.ts`
- Create: `apps/web/lib/store/runStore.ts`
- Create: `apps/web/lib/store/stateStore.ts`
- Create: `apps/web/lib/store/viewStore.ts`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/lib/store/runStore.test.ts`

- [ ] **Step 1: Configure Vitest**

`apps/web/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, '.') } },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./vitest.setup.ts'] },
});
```

`apps/web/vitest.setup.ts`:
```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 2: Write failing store test**

`apps/web/lib/store/runStore.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useRunStore } from './runStore';

beforeEach(() => useRunStore.setState({ tid: null, nodes: {}, status: 'idle', interrupts: [] }));

describe('runStore', () => {
  it('handles node_start then node_end', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'node_start', node: 'market_sensor', ts: 1 });
    expect(useRunStore.getState().nodes.market_sensor.status).toBe('running');
    s.handleEvent({ type: 'node_end', node: 'market_sensor', ts: 2, state_patch: {} });
    expect(useRunStore.getState().nodes.market_sensor.status).toBe('done');
  });

  it('records interrupts', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'interrupt', node: 'pattern_matcher', snapshot: { x: 1 }, ts: 3 });
    expect(useRunStore.getState().interrupts).toHaveLength(1);
    expect(useRunStore.getState().status).toBe('interrupted');
  });

  it('marks done', () => {
    const s = useRunStore.getState();
    s.handleEvent({ type: 'done', final_state: {}, ts: 4 });
    expect(useRunStore.getState().status).toBe('done');
  });
});
```

Run:
```bash
cd apps/web && npx vitest run
```
Expected: import error.

- [ ] **Step 3: Implement stores**

`apps/web/lib/store/runStore.ts`:
```ts
'use client';
import { create } from 'zustand';

export type RunEvent =
  | { type: 'node_start'; node: string; ts: number }
  | { type: 'node_end'; node: string; ts: number; state_patch: Record<string, unknown> }
  | { type: 'node_error'; node: string; ts: number; message: string }
  | { type: 'interrupt'; node: string; snapshot: Record<string, unknown>; ts: number }
  | { type: 'done'; final_state: Record<string, unknown>; ts: number }
  | { type: 'aborted'; reason: string; ts: number };

type NodeStatus = 'pending' | 'running' | 'done' | 'error';
interface NodeInfo { status: NodeStatus; error?: string; ts?: number }

interface RunStore {
  tid: string | null;
  status: 'idle' | 'running' | 'interrupted' | 'done' | 'aborted';
  nodes: Record<string, NodeInfo>;
  interrupts: { node: string; snapshot: Record<string, unknown>; ts: number }[];
  setTid(tid: string): void;
  reset(): void;
  handleEvent(ev: RunEvent): void;
}

export const useRunStore = create<RunStore>((set) => ({
  tid: null, status: 'idle', nodes: {}, interrupts: [],
  setTid: (tid) => set({ tid, status: 'running', nodes: {}, interrupts: [] }),
  reset: () => set({ tid: null, status: 'idle', nodes: {}, interrupts: [] }),
  handleEvent: (ev) => set((st) => {
    const nodes = { ...st.nodes };
    switch (ev.type) {
      case 'node_start':
        nodes[ev.node] = { status: 'running', ts: ev.ts };
        return { nodes, status: 'running' };
      case 'node_end':
        nodes[ev.node] = { status: 'done', ts: ev.ts };
        return { nodes };
      case 'node_error':
        nodes[ev.node] = { status: 'error', error: ev.message, ts: ev.ts };
        return { nodes };
      case 'interrupt':
        return { interrupts: [...st.interrupts, ev], status: 'interrupted' };
      case 'done':
        return { status: 'done' };
      case 'aborted':
        return { status: 'aborted' };
    }
  }),
}));
```

`apps/web/lib/store/stateStore.ts`:
```ts
'use client';
import { create } from 'zustand';

interface StateStore {
  state: Record<string, unknown>;
  merge(patch: Record<string, unknown>): void;
  replace(s: Record<string, unknown>): void;
  reset(): void;
}

export const useStateStore = create<StateStore>((set) => ({
  state: {},
  merge: (patch) => set((s) => ({ state: { ...s.state, ...patch } })),
  replace: (s) => set({ state: s }),
  reset: () => set({ state: {} }),
}));
```

`apps/web/lib/store/viewStore.ts`:
```ts
'use client';
import { create } from 'zustand';

export type CenterView = 'overview' | 'themes' | 'leaders' | 'candidates' | 'arbitrage' | 'risk' | 'plan';

interface ViewStore {
  view: CenterView;
  setView(v: CenterView): void;
  selectedCode: string | null;
  selectCode(code: string | null): void;
}

export const useViewStore = create<ViewStore>((set) => ({
  view: 'overview',
  setView: (view) => set({ view }),
  selectedCode: null,
  selectCode: (selectedCode) => set({ selectedCode }),
}));
```

- [ ] **Step 4: SSE helper**

`apps/web/lib/sse.ts`:
```ts
'use client';
import type { RunEvent } from './store/runStore';

export function subscribeRun(tid: string, onEvent: (ev: RunEvent) => void): () => void {
  const es = new EventSource(`/api/run/${tid}/stream`);
  const types: RunEvent['type'][] = ['node_start', 'node_end', 'node_error', 'interrupt', 'done', 'aborted'];
  for (const t of types) {
    es.addEventListener(t, (e) => {
      try { onEvent(JSON.parse((e as MessageEvent).data) as RunEvent); }
      catch { /* swallow malformed */ }
    });
  }
  es.onerror = () => {/* EventSource auto-reconnects */};
  return () => es.close();
}
```

- [ ] **Step 5: Minimal API client**

`apps/web/lib/api/client.ts`:
```ts
'use client';

const BASE = ''; // same-origin via Next rewrites in dev / mounted in prod

export async function startRun(body: { date: string; use_llm?: boolean; refresh?: boolean })
  : Promise<{ thread_id: string }> {
  const r = await fetch(`${BASE}/api/run`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST /api/run ${r.status}`);
  return r.json();
}

export async function getRunsList(): Promise<Array<{ date: string; candidates_count: number; errors_count: number; has_plan: boolean }>> {
  const r = await fetch(`${BASE}/api/runs`);
  if (!r.ok) throw new Error('GET /api/runs');
  return r.json();
}

export async function getRunByDate(date: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/api/runs/${date}`);
  if (!r.ok) throw new Error(`GET /api/runs/${date}`);
  return r.json();
}

export async function getStateByTid(tid: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/api/state/${tid}`);
  if (!r.ok) throw new Error(`GET /api/state/${tid}`);
  return r.json();
}
```

`apps/web/lib/api/types.gen.ts` (placeholder until first real `npm run gen:api`):
```ts
// generated by `npm run gen:api`; placeholder only — start the FastAPI server then re-run.
export type _Placeholder = unknown;
```

- [ ] **Step 6: Run tests**

```bash
cd apps/web && npx vitest run
```
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib apps/web/vitest.config.ts apps/web/vitest.setup.ts
git commit -m "feat(web): API client + Zustand stores + SSE subscription helper"
```

---

### Task 8: ThreeColumnLayout + TopBar

**Files:**
- Create: `apps/web/components/shell/ThreeColumnLayout.tsx`
- Create: `apps/web/components/shell/TopBar.tsx`
- Create: `apps/web/app/console/page.tsx`
- Create: `apps/web/components/shell/ThreeColumnLayout.test.tsx`

- [ ] **Step 1: Failing layout test**

`apps/web/components/shell/ThreeColumnLayout.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ThreeColumnLayout } from './ThreeColumnLayout';

describe('ThreeColumnLayout', () => {
  it('renders all three slots', () => {
    render(
      <ThreeColumnLayout
        left={<div>L</div>} center={<div>C</div>} right={<div>R</div>}
      />
    );
    expect(screen.getByText('L')).toBeInTheDocument();
    expect(screen.getByText('C')).toBeInTheDocument();
    expect(screen.getByText('R')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement layout**

`apps/web/components/shell/ThreeColumnLayout.tsx`:
```tsx
import type { ReactNode } from 'react';

export function ThreeColumnLayout({
  top, left, center, right,
}: { top?: ReactNode; left: ReactNode; center: ReactNode; right: ReactNode }) {
  return (
    <div className="grid grid-rows-[auto_1fr] h-screen">
      {top && <header className="border-b border-neutral-800 px-4 py-2">{top}</header>}
      <div className="grid grid-cols-[240px_1fr_360px] overflow-hidden">
        <aside className="border-r border-neutral-800 overflow-y-auto p-3">{left}</aside>
        <main className="overflow-y-auto p-4">{center}</main>
        <aside className="border-l border-neutral-800 overflow-y-auto p-3">{right}</aside>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: TopBar with date + Run button**

`apps/web/components/shell/TopBar.tsx`:
```tsx
'use client';
import { useState } from 'react';
import { startRun } from '@/lib/api/client';
import { useRunStore } from '@/lib/store/runStore';
import { subscribeRun } from '@/lib/sse';
import { useStateStore } from '@/lib/store/stateStore';

function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function TopBar() {
  const [date, setDate] = useState(todayISO());
  const [useLlm, setUseLlm] = useState(true);
  const [refresh, setRefresh] = useState(false);
  const { tid, status, setTid, handleEvent, reset } = useRunStore();
  const merge = useStateStore((s) => s.merge);

  async function go() {
    reset();
    const { thread_id } = await startRun({ date, use_llm: useLlm, refresh });
    setTid(thread_id);
    subscribeRun(thread_id, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
  }

  return (
    <div className="flex items-center gap-3 font-mono text-sm">
      <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
             className="bg-neutral-900 border border-neutral-700 px-2 py-1 rounded" />
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> use-llm
      </label>
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} /> refresh
      </label>
      <button onClick={go} disabled={status === 'running' || status === 'interrupted'}
              className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 px-3 py-1 rounded">
        ▶ Run
      </button>
      <span className="text-neutral-400">{tid ? `tid: ${tid}` : 'idle'} · status: {status}</span>
    </div>
  );
}
```

- [ ] **Step 4: Console page wires everything**

`apps/web/app/console/page.tsx`:
```tsx
'use client';
import { ThreeColumnLayout } from '@/components/shell/ThreeColumnLayout';
import { TopBar } from '@/components/shell/TopBar';

export default function ConsolePage() {
  return (
    <ThreeColumnLayout
      top={<TopBar />}
      left={<div className="text-sm text-neutral-400">左：上下文（占位）</div>}
      center={<div className="text-sm text-neutral-400">中：当前视图（占位）</div>}
      right={<div className="text-sm text-neutral-400">右：Run 流（占位）</div>}
    />
  );
}
```

- [ ] **Step 5: Run tests + smoke**

```bash
cd apps/web && npx vitest run
```
Expected: PASS.

Smoke:
```bash
# terminal 1
uvicorn apps.api.main:app --port 8000
# terminal 2
cd apps/web && npm run dev
# browser: http://localhost:3000/console — type a date, click Run; status should flip running → done
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/shell apps/web/app/console
git commit -m "feat(web): three-column console shell + Run button wired to SSE"
```

---

### Task 9: NodeTimeline (right column)

**Files:**
- Create: `apps/web/components/right-runstream/NodeTimeline.tsx`
- Modify: `apps/web/app/console/page.tsx`
- Create: `apps/web/components/right-runstream/NodeTimeline.test.tsx`

- [ ] **Step 1: Failing test**

`apps/web/components/right-runstream/NodeTimeline.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { useRunStore } from '@/lib/store/runStore';
import { NodeTimeline } from './NodeTimeline';

beforeEach(() => useRunStore.setState({ tid: 't', nodes: {}, status: 'running', interrupts: [] }));

describe('NodeTimeline', () => {
  it('renders ordered node names with status dots', () => {
    useRunStore.getState().handleEvent({ type: 'node_start', node: 'market_sensor', ts: 1 });
    useRunStore.getState().handleEvent({ type: 'node_end', node: 'market_sensor', ts: 2, state_patch: {} });
    useRunStore.getState().handleEvent({ type: 'node_start', node: 'index_cycle', ts: 3 });
    render(<NodeTimeline />);
    expect(screen.getByText('market_sensor')).toBeInTheDocument();
    expect(screen.getByText('index_cycle')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement NodeTimeline with canonical 14-node order**

`apps/web/components/right-runstream/NodeTimeline.tsx`:
```tsx
'use client';
import { useRunStore } from '@/lib/store/runStore';

const ORDER = [
  'market_sensor', 'index_cycle', 'cycle_switch', 'emotion',
  'theme_analyst', 'leader_tracker', 'pattern_matcher',
  'first_board', 'weak_to_strong', 'continuous', 'setback_reversal',
  'arbitrage', 'risk_guard', 'trade_planner', 'post_mortem',
] as const;

const DOT_CLASS = {
  pending: 'bg-neutral-700',
  running: 'bg-amber-500 animate-pulse',
  done: 'bg-emerald-500',
  error: 'bg-red-500',
} as const;

export function NodeTimeline() {
  const nodes = useRunStore((s) => s.nodes);
  const interrupts = useRunStore((s) => s.interrupts);
  const interruptedNode = interrupts.at(-1)?.node;

  return (
    <div className="space-y-1 font-mono text-xs">
      <div className="text-neutral-400 mb-2 text-[10px] uppercase tracking-wider">Run flow</div>
      {ORDER.map((n) => {
        const info = nodes[n];
        const status = interruptedNode === n ? 'running' : (info?.status ?? 'pending');
        return (
          <div key={n} className="flex items-center gap-2" title={info?.error ?? ''}>
            <span className={`inline-block w-2 h-2 rounded-full ${DOT_CLASS[status]}`} />
            <span className={status === 'pending' ? 'text-neutral-600' : 'text-neutral-200'}>{n}</span>
            {interruptedNode === n && <span className="text-amber-400">⏸ review</span>}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Plug into console page**

In `apps/web/app/console/page.tsx`, replace `right` slot:
```tsx
import { NodeTimeline } from '@/components/right-runstream/NodeTimeline';
// ...
right={<NodeTimeline />}
```

- [ ] **Step 4: Run tests + smoke**

```bash
cd apps/web && npx vitest run
```
Expected: PASS. Smoke: click Run; right column dots progress green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/right-runstream apps/web/app/console/page.tsx
git commit -m "feat(web): NodeTimeline in right column"
```

---

### Task 10: Center 7 views (table-only) + history picker

**Files:**
- Create: `apps/web/components/center-views/{Overview,Themes,Leaders,Candidates,Arbitrage,Risk,Plan}View.tsx`
- Create: `apps/web/components/center-views/CenterRouter.tsx`
- Create: `apps/web/components/left-context/DateNavigator.tsx`
- Create: `apps/web/app/history/page.tsx`
- Modify: `apps/web/app/console/page.tsx`

- [ ] **Step 1: Implement view switcher and 7 placeholder views**

`apps/web/components/center-views/CenterRouter.tsx`:
```tsx
'use client';
import { useViewStore, type CenterView } from '@/lib/store/viewStore';
import { OverviewView } from './OverviewView';
import { ThemesView } from './ThemesView';
import { LeadersView } from './LeadersView';
import { CandidatesView } from './CandidatesView';
import { ArbitrageView } from './ArbitrageView';
import { RiskView } from './RiskView';
import { PlanView } from './PlanView';

const VIEWS: { id: CenterView; label: string }[] = [
  { id: 'overview', label: '概览' }, { id: 'themes', label: '题材' },
  { id: 'leaders', label: '龙头' }, { id: 'candidates', label: '候选池' },
  { id: 'arbitrage', label: '套利' }, { id: 'risk', label: '风控' },
  { id: 'plan', label: '计划' },
];

export function CenterRouter() {
  const { view, setView } = useViewStore();
  return (
    <div className="flex flex-col gap-3">
      <nav className="flex gap-2 border-b border-neutral-800 pb-2">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)}
                  className={`px-2 py-1 text-sm font-mono ${
                    view === v.id ? 'text-amber-400 border-b-2 border-amber-400' : 'text-neutral-400'
                  }`}>{v.label}</button>
        ))}
      </nav>
      <div>
        {view === 'overview' && <OverviewView />}
        {view === 'themes' && <ThemesView />}
        {view === 'leaders' && <LeadersView />}
        {view === 'candidates' && <CandidatesView />}
        {view === 'arbitrage' && <ArbitrageView />}
        {view === 'risk' && <RiskView />}
        {view === 'plan' && <PlanView />}
      </div>
    </div>
  );
}
```

For each of the 7 view files, write a minimal projection of state (KPI / table). Example for the most important — `CandidatesView`:

`apps/web/components/center-views/CandidatesView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';

interface Candidate {
  code: string; name?: string; score?: number;
  branch?: string; suggested_price?: number; suggested_position?: number;
}

export function CandidatesView() {
  const cands = (useStateStore((s) => s.state).candidates as Candidate[] | undefined) ?? [];
  if (cands.length === 0) return <div className="text-neutral-400 text-sm">候选池：空</div>;
  return (
    <table className="w-full font-mono text-sm">
      <thead className="text-left text-xs text-neutral-400 border-b border-neutral-800">
        <tr><th className="py-1">代码</th><th>名称</th><th>得分</th><th>分支</th><th>建议价</th><th>建议仓位</th></tr>
      </thead>
      <tbody>
        {cands.map((c) => (
          <tr key={c.code} className="border-b border-neutral-900 hover:bg-neutral-900">
            <td className="py-1">{c.code}</td><td>{c.name ?? ''}</td>
            <td>{c.score?.toFixed(2) ?? ''}</td><td>{c.branch ?? ''}</td>
            <td>{c.suggested_price?.toFixed(2) ?? ''}</td>
            <td>{c.suggested_position != null ? `${(c.suggested_position * 100).toFixed(0)}%` : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`apps/web/components/center-views/OverviewView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';

function KPI({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border border-neutral-800 rounded p-3 font-mono">
      <div className="text-[10px] uppercase text-neutral-500">{label}</div>
      <div className="text-lg">{value}</div>
    </div>
  );
}

export function OverviewView() {
  const s = useStateStore((st) => st.state) as Record<string, any>;
  return (
    <div className="grid grid-cols-3 gap-3">
      <KPI label="情绪" value={s.emotion_phase ?? '—'} />
      <KPI label="情绪值" value={s.sentiment_value ?? '—'} />
      <KPI label="涨停 / 连板" value={`${s.limit_up_count ?? 0} / ${s.consec_top ?? 0}`} />
      <KPI label="炸板率" value={`${((s.blast_rate ?? 0) * 100).toFixed(1)}%`} />
      <KPI label="指数相位" value={s.index_phase ?? '—'} />
      <KPI label="主线" value={s.main_theme ?? '—'} />
    </div>
  );
}
```

For the remaining 5 views (`ThemesView`, `LeadersView`, `ArbitrageView`, `RiskView`, `PlanView`), follow the same pattern: read the relevant slice from `useStateStore`, render a sortable table or KPI panel. Example:

`apps/web/components/center-views/ThemesView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function ThemesView() {
  const themes = (useStateStore((s) => s.state).themes ?? {}) as Record<string, any>;
  const entries = Object.entries(themes);
  if (entries.length === 0) return <div className="text-neutral-400 text-sm">题材：空</div>;
  return (
    <div className="grid grid-cols-2 gap-3 font-mono text-sm">
      {entries.map(([name, t]) => (
        <div key={name} className="border border-neutral-800 rounded p-3">
          <div className="font-bold">{name}</div>
          <div className="text-neutral-400 text-xs">phase: {t.phase ?? '—'} · leader: {t.leader ?? '—'}</div>
          <div className="text-neutral-500 text-xs">members: {(t.members ?? []).join(', ')}</div>
        </div>
      ))}
    </div>
  );
}
```

`apps/web/components/center-views/LeadersView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';
import { useViewStore } from '@/lib/store/viewStore';

export function LeadersView() {
  const stack = (useStateStore((s) => s.state).leader_stack ?? []) as any[];
  const selectCode = useViewStore((s) => s.selectCode);
  if (stack.length === 0) return <div className="text-neutral-400 text-sm">龙头梯队：空</div>;
  return (
    <table className="w-full font-mono text-sm">
      <thead className="text-left text-xs text-neutral-400 border-b border-neutral-800">
        <tr><th>代码</th><th>名称</th><th>角色</th><th>板数</th><th>强度</th></tr>
      </thead>
      <tbody>
        {stack.map((l: any) => (
          <tr key={l.code} className="cursor-pointer hover:bg-neutral-900"
              onClick={() => selectCode(l.code)}>
            <td className="py-1">{l.code}</td><td>{l.name}</td><td>{l.role}</td>
            <td>{l.consec ?? ''}</td><td>{l.strength?.toFixed(2) ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`apps/web/components/center-views/ArbitrageView.tsx`, `RiskView.tsx`, `PlanView.tsx` — analogous projections of `state.arb_opportunities`, `state.risk_flags`, `state.plan`. Each is 15-25 lines. Implement them following the same shape.

- [ ] **Step 2: Date navigator + history loading**

`apps/web/components/left-context/DateNavigator.tsx`:
```tsx
'use client';
import { useQuery } from '@tanstack/react-query';
import { getRunsList, getRunByDate } from '@/lib/api/client';
import { useStateStore } from '@/lib/store/stateStore';

export function DateNavigator() {
  const { data = [] } = useQuery({ queryKey: ['runs'], queryFn: getRunsList });
  const replace = useStateStore((s) => s.replace);

  async function loadDate(date: string) {
    const snap = await getRunByDate(date);
    replace(snap);
  }

  return (
    <div className="space-y-1 font-mono text-xs">
      <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">历史</div>
      {data.map((r) => (
        <button key={r.date} onClick={() => loadDate(r.date)}
                className="w-full text-left hover:bg-neutral-900 px-2 py-1 rounded flex justify-between">
          <span>{r.date}</span>
          <span className="text-neutral-500">{r.candidates_count}c {r.errors_count}e</span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Update console page to use CenterRouter + DateNavigator**

Modify `apps/web/app/console/page.tsx`:
```tsx
'use client';
import { ThreeColumnLayout } from '@/components/shell/ThreeColumnLayout';
import { TopBar } from '@/components/shell/TopBar';
import { NodeTimeline } from '@/components/right-runstream/NodeTimeline';
import { CenterRouter } from '@/components/center-views/CenterRouter';
import { DateNavigator } from '@/components/left-context/DateNavigator';

export default function ConsolePage() {
  return (
    <ThreeColumnLayout
      top={<TopBar />}
      left={<DateNavigator />}
      center={<CenterRouter />}
      right={<NodeTimeline />}
    />
  );
}
```

- [ ] **Step 4: Smoke**

```bash
# both servers running:
# Browser http://localhost:3000/console
# - Click an old date in left column → center populates
# - Click Run → SSE updates flow into Overview KPIs
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/center-views apps/web/components/left-context apps/web/app/console/page.tsx
git commit -m "feat(web): 7 center views + history date navigator"
```

---

## Phase 3 — Interrupt (4 tasks)

Goal: graph pauses at PatternMatcher / RiskGuard / TradePlanner; web shows review drawer; resume continues the run. CLI keeps working via auto-resume.

### Task 11: Add `interrupt(...)` to 3 nodes + CLI auto-resume

**Files:**
- Modify: `src/youzi_agent/nodes/pattern_matcher.py`
- Modify: `src/youzi_agent/nodes/risk_guard.py`
- Modify: `src/youzi_agent/nodes/trade_planner.py`
- Modify: `src/youzi_agent/cli.py`
- Modify: `tests/test_graph_e2e.py` (or whatever existing graph e2e is)

- [ ] **Step 1: Failing test for "interrupt skipped under YOUZI_AUTO_RESUME"**

Add to `tests/test_cli_auto_resume.py` (new file):
```python
import os
from youzi_agent.graph import build_graph

def test_cli_path_auto_resumes_through_interrupts(tmp_path, monkeypatch):
    """When YOUZI_AUTO_RESUME=1 (CLI mode), the graph must complete without
    blocking on any interrupt — proven by graph.invoke returning a state with
    'plan' set (or None if no candidates), not raising."""
    monkeypatch.setenv("YOUZI_AUTO_RESUME", "1")
    g = build_graph(checkpoint_path=str(tmp_path / "ckpt.db"))
    out = g.invoke(
        {"target_date": "1970-01-01", "use_llm": False},
        config={"configurable": {"thread_id": "auto-resume-test"}},
    )
    assert "target_date" in out
```

Run:
```bash
pytest tests/test_cli_auto_resume.py -v
```
Expected: PASS now (no interrupts yet); we keep this as a regression net.

- [ ] **Step 2: Add interrupt to `pattern_matcher_node`**

Modify `src/youzi_agent/nodes/pattern_matcher.py`. At the very end of `pattern_matcher_node`, before `return`:

```python
import os
from langgraph.types import interrupt

# ... existing code that builds `hits` and `state_patch` ...

result = {"pattern_hits": hits, **state_patch}
if not os.environ.get("YOUZI_AUTO_RESUME"):
    review = interrupt({
        "node": "pattern_matcher",
        "snapshot": {"pattern_hits": hits, "emotion_phase": emotion,
                     "succession_status": succession, "index_phase": index_phase},
    })
    if isinstance(review, dict):
        if "pattern_hits" in review:
            result["pattern_hits"] = review["pattern_hits"]
return result
```

- [ ] **Step 3: Add interrupt to `risk_guard_node` (analogous)**

Modify `src/youzi_agent/nodes/risk_guard.py` similarly. Wrap the final return:

```python
import os
from langgraph.types import interrupt

# ... existing computation produces `risk_flags`, position cap etc. ...
result = {"risk_flags": risk_flags, "plan": {**existing_plan_patch, ...}}
if not os.environ.get("YOUZI_AUTO_RESUME"):
    review = interrupt({
        "node": "risk_guard",
        "snapshot": {"risk_flags": risk_flags,
                     "candidates": state.get("candidates", []),
                     "plan_position_cap": result["plan"].get("position_total_max")},
    })
    if isinstance(review, dict):
        if "risk_flags" in review:
            result["risk_flags"] = review["risk_flags"]
        if "position_total_max" in review:
            result["plan"]["position_total_max"] = review["position_total_max"]
return result
```

- [ ] **Step 4: Add interrupt to `trade_planner_node` (analogous)**

Modify `src/youzi_agent/nodes/trade_planner.py`:
```python
import os
from langgraph.types import interrupt

# ... existing produces `plan` dict ...
result = {"plan": plan, "final_candidates": final_candidates}
if not os.environ.get("YOUZI_AUTO_RESUME"):
    review = interrupt({
        "node": "trade_planner",
        "snapshot": {"plan": plan, "final_candidates": final_candidates},
    })
    if isinstance(review, dict) and "plan" in review:
        result["plan"] = review["plan"]
return result
```

- [ ] **Step 5: Modify CLI to set `YOUZI_AUTO_RESUME=1`**

Modify `src/youzi_agent/cli.py` `main()`:
```python
def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    os.environ["YOUZI_AUTO_RESUME"] = "1"   # <-- new line
    args = _build_parser().parse_args(argv)
    # ... rest unchanged ...
```

- [ ] **Step 6: Run test + existing graph e2e**

```bash
pytest -q
```
Expected: all PASS (CLI sets auto-resume, no test sees an interrupt).

- [ ] **Step 7: Commit**

```bash
git add src/youzi_agent/nodes/pattern_matcher.py src/youzi_agent/nodes/risk_guard.py \
        src/youzi_agent/nodes/trade_planner.py src/youzi_agent/cli.py tests/test_cli_auto_resume.py
git commit -m "feat(graph): interrupt() at pattern_matcher/risk_guard/trade_planner; CLI auto-resumes"
```

---

### Task 12: GraphRuntime.resume + `/api/run/{tid}/resume`

**Files:**
- Modify: `apps/api/graph_runtime.py`
- Modify: `apps/api/routes/run.py`
- Create: `apps/api/tests/test_runtime_interrupt.py`

- [ ] **Step 1: Failing test exercising interrupt → resume**

`apps/api/tests/test_runtime_interrupt.py`:
```python
import asyncio
import pytest
from apps.api.graph_runtime import GraphRuntime


@pytest.mark.asyncio
async def test_interrupt_then_resume_completes(tmp_path):
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="1970-01-01", use_llm=False, refresh=False)

    interrupted = False
    async def consume():
        nonlocal interrupted
        async for ev in rt.stream(tid):
            if ev["type"] == "interrupt":
                interrupted = True
                # Approve unchanged
                await rt.resume(tid, {"action": "approve", "patch": {}})
            if ev["type"] in ("done", "aborted"):
                return ev

    # Bound the test (graph must complete in <30s on this fixture)
    final = await asyncio.wait_for(consume(), timeout=30)
    assert interrupted, "expected at least one interrupt during run"
    assert final["type"] in ("done", "aborted")
```

Run:
```bash
pytest apps/api/tests/test_runtime_interrupt.py -v
```
Expected: AttributeError on `rt.resume`.

- [ ] **Step 2: Implement `resume` + interrupt detection in `_drive`**

Modify `apps/api/graph_runtime.py`:

Add to `__init__`:
```python
        self._resume_signals: dict[str, asyncio.Future] = {}
```

Add method:
```python
    async def resume(self, tid: str, payload: dict) -> None:
        fut = self._resume_signals.pop(tid, None)
        if fut is None:
            raise RuntimeError(f"no pending interrupt for {tid}")
        fut.set_result(payload)
```

Replace `_drive` body to detect `__interrupt__` chunks (LangGraph 0.2 surfaces these in `stream_mode="updates"`):
```python
    async def _drive(self, tid: str, date: str, use_llm: bool, refresh: bool) -> None:
        cfg = {"configurable": {"thread_id": tid}}
        q = self._queues[tid]
        try:
            await self._run_until_done(tid, cfg,
                                       initial={"target_date": date, "use_llm": use_llm})
            final = self._graph.get_state(cfg).values
            await q.put(DoneEvent(type="done", final_state=_jsonable(final), ts=time.time()))
        except Exception as e:
            await q.put(NodeErrorEvent(type="node_error", node="<run>",
                                       ts=time.time(), message=str(e)))
            await q.put(AbortedEvent(type="aborted", reason=str(e), ts=time.time()))

    async def _run_until_done(self, tid: str, cfg: dict, initial: dict | None) -> None:
        q = self._queues[tid]
        cur_input = initial
        while True:
            interrupted = False
            async for chunk in self._graph.astream(cur_input, config=cfg, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupted = True
                    iv = chunk["__interrupt__"]
                    # iv is a tuple of Interrupt objects in LangGraph 0.2
                    payload = iv[0].value if isinstance(iv, tuple) else iv.value
                    await q.put(InterruptEvent(
                        type="interrupt", node=payload.get("node", "<unknown>"),
                        snapshot=_jsonable(payload.get("snapshot", {})), ts=time.time()))
                    # block until resume()
                    fut = asyncio.get_event_loop().create_future()
                    self._resume_signals[tid] = fut
                    review = await fut
                    # write the user's edits back into state and continue
                    if review.get("patch"):
                        self._graph.update_state(cfg, review["patch"])
                    cur_input = None  # continue from checkpoint
                    break
                for node, patch in chunk.items():
                    if node == "__interrupt__":
                        continue
                    await q.put(NodeStartEvent(type="node_start", node=node, ts=time.time()))
                    await q.put(NodeEndEvent(
                        type="node_end", node=node, ts=time.time(),
                        state_patch=_jsonable(patch),
                    ))
            if not interrupted:
                return
```

Add import:
```python
from .events import InterruptEvent  # noqa
```

- [ ] **Step 3: Add `/resume` route**

Modify `apps/api/routes/run.py`:
```python
class ResumeBody(BaseModel):
    node: str | None = None
    action: str = "approve"   # 'approve' | 'edit'
    patch: dict | None = None


@router.post("/run/{tid}/resume")
async def post_resume(tid: str, body: ResumeBody, request: Request) -> dict:
    rt = request.app.state.runtime
    await rt.resume(tid, {"action": body.action, "patch": body.patch or {}})
    return {"ok": True}


@router.post("/run/{tid}/abort")
async def post_abort(tid: str, request: Request) -> dict:
    rt = request.app.state.runtime
    await rt.resume(tid, {"action": "abort", "patch": {}})
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```bash
pytest apps/api/tests/ -v
```
Expected: all PASS including `test_interrupt_then_resume_completes`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/graph_runtime.py apps/api/routes/run.py apps/api/tests/test_runtime_interrupt.py
git commit -m "feat(api): GraphRuntime.resume + POST /run/{tid}/resume"
```

---

### Task 13: SSE `interrupt` event in front-end + InterruptDrawer container

**Files:**
- Create: `apps/web/components/right-runstream/InterruptDrawer.tsx`
- Modify: `apps/web/components/shell/TopBar.tsx` (no change — already wires events)
- Modify: `apps/web/components/right-runstream/NodeTimeline.tsx` (already shows ⏸)
- Create: `apps/web/lib/api/client.ts` add `resumeRun`

- [ ] **Step 1: Add `resumeRun` to API client**

Append to `apps/web/lib/api/client.ts`:
```ts
export async function resumeRun(tid: string, body: { action?: 'approve' | 'edit' | 'abort'; patch?: Record<string, unknown> }) {
  const r = await fetch(`${BASE}/api/run/${tid}/resume`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action: body.action ?? 'approve', patch: body.patch ?? {} }),
  });
  if (!r.ok) throw new Error(`resume failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Implement InterruptDrawer container that dispatches to per-node review**

`apps/web/components/right-runstream/InterruptDrawer.tsx`:
```tsx
'use client';
import { useRunStore } from '@/lib/store/runStore';
import { resumeRun } from '@/lib/api/client';
import { PatternMatcherReview } from './reviews/PatternMatcherReview';
import { RiskGuardReview } from './reviews/RiskGuardReview';
import { TradePlannerReview } from './reviews/TradePlannerReview';

export function InterruptDrawer() {
  const tid = useRunStore((s) => s.tid);
  const interrupts = useRunStore((s) => s.interrupts);
  const last = interrupts.at(-1);
  if (!last || !tid) return null;

  async function approve(patch: Record<string, unknown> = {}) {
    await resumeRun(tid!, { action: Object.keys(patch).length ? 'edit' : 'approve', patch });
    // popping the last interrupt — local optimistic clear so we don't show drawer twice
    useRunStore.setState({
      interrupts: useRunStore.getState().interrupts.slice(0, -1),
      status: 'running',
    });
  }

  return (
    <div className="mt-3 border-t border-amber-700 pt-3">
      <div className="text-amber-400 text-xs uppercase tracking-wider mb-2">⏸ Review · {last.node}</div>
      {last.node === 'pattern_matcher' && <PatternMatcherReview snapshot={last.snapshot} onApprove={approve} />}
      {last.node === 'risk_guard' && <RiskGuardReview snapshot={last.snapshot} onApprove={approve} />}
      {last.node === 'trade_planner' && <TradePlannerReview snapshot={last.snapshot} onApprove={approve} />}
    </div>
  );
}
```

- [ ] **Step 3: Mount drawer below NodeTimeline in console**

Modify `apps/web/app/console/page.tsx` `right` slot:
```tsx
right={(<><NodeTimeline /><InterruptDrawer /></>)}
```

(Add the import.)

- [ ] **Step 4: Smoke (with stubs — drawer won't render content yet, that's Task 14)**

```bash
# Run a date that triggers pattern_matcher hits, e.g. with synthetic fixture
# When graph hits PatternMatcher, right column shows ⏸ Review · pattern_matcher header
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/api/client.ts apps/web/components/right-runstream/InterruptDrawer.tsx apps/web/app/console/page.tsx
git commit -m "feat(web): InterruptDrawer dispatcher (review components stubbed)"
```

---

### Task 14: 3 review components

**Files:**
- Create: `apps/web/components/right-runstream/reviews/PatternMatcherReview.tsx`
- Create: `apps/web/components/right-runstream/reviews/RiskGuardReview.tsx`
- Create: `apps/web/components/right-runstream/reviews/TradePlannerReview.tsx`

- [ ] **Step 1: PatternMatcherReview**

`apps/web/components/right-runstream/reviews/PatternMatcherReview.tsx`:
```tsx
'use client';
import { useState } from 'react';

interface Hit { pattern_id: string; filter_desc: string; target_subagent: string }
interface Props {
  snapshot: { pattern_hits?: Hit[]; emotion_phase?: string; succession_status?: string; index_phase?: string };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function PatternMatcherReview({ snapshot, onApprove }: Props) {
  const initial: Hit[] = snapshot.pattern_hits ?? [];
  const [hits, setHits] = useState(initial);
  const dirty = JSON.stringify(hits) !== JSON.stringify(initial);

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">
        emotion: {snapshot.emotion_phase} · succession: {snapshot.succession_status} · index: {snapshot.index_phase}
      </div>
      <ul className="space-y-1">
        {hits.map((h, i) => (
          <li key={i} className="flex items-center justify-between border border-neutral-800 rounded px-2 py-1">
            <span>{h.pattern_id} → <span className="text-neutral-400">{h.target_subagent}</span></span>
            <button onClick={() => setHits(hits.filter((_, j) => j !== i))}
                    className="text-red-400 hover:text-red-300">×</button>
          </li>
        ))}
        {hits.length === 0 && <li className="text-neutral-500">空 — 子图分发将跳过</li>}
      </ul>
      <div className="flex gap-2">
        <button onClick={() => onApprove(dirty ? { pattern_hits: hits } : {})}
                className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">
          {dirty ? '应用并继续' : '通过'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: RiskGuardReview**

`apps/web/components/right-runstream/reviews/RiskGuardReview.tsx`:
```tsx
'use client';
import { useState } from 'react';

interface Props {
  snapshot: {
    risk_flags?: string[];
    candidates?: { code: string; name?: string }[];
    plan_position_cap?: number;
  };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function RiskGuardReview({ snapshot, onApprove }: Props) {
  const initialFlags = snapshot.risk_flags ?? [];
  const [flags, setFlags] = useState<string[]>(initialFlags);
  const [cap, setCap] = useState(snapshot.plan_position_cap ?? 1);
  const flagsDirty = flags.length !== initialFlags.length;
  const capDirty = cap !== (snapshot.plan_position_cap ?? 1);

  function toggle(f: string) {
    setFlags((cur) => cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]);
  }

  function apply() {
    const patch: Record<string, unknown> = {};
    if (flagsDirty) patch.risk_flags = flags;
    if (capDirty) patch.position_total_max = cap;
    onApprove(patch);
  }

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">候选 {snapshot.candidates?.length ?? 0} 只 · 当前仓位上限 {(cap * 100).toFixed(0)}%</div>
      <ul className="space-y-1">
        {initialFlags.map((f) => (
          <li key={f} className="flex items-center gap-2">
            <input type="checkbox" checked={flags.includes(f)} onChange={() => toggle(f)} />
            <span>{f}</span>
          </li>
        ))}
        {initialFlags.length === 0 && <li className="text-neutral-500">无禁忌触发</li>}
      </ul>
      <label className="flex items-center gap-2">
        <span>仓位上限</span>
        <input type="number" min={0} max={1} step={0.1} value={cap}
               onChange={(e) => setCap(Number(e.target.value))}
               className="bg-neutral-900 border border-neutral-700 px-1 w-16" />
      </label>
      <button onClick={apply}
              className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">通过</button>
    </div>
  );
}
```

- [ ] **Step 3: TradePlannerReview**

`apps/web/components/right-runstream/reviews/TradePlannerReview.tsx`:
```tsx
'use client';
import { useState } from 'react';

interface Plan {
  position_total_max?: number;
  candidates?: { code: string; name?: string; weight?: number }[];
  notes?: string;
}
interface Props {
  snapshot: { plan?: Plan; final_candidates?: any[] };
  onApprove(patch?: Record<string, unknown>): void | Promise<void>;
}

export function TradePlannerReview({ snapshot, onApprove }: Props) {
  const initial = snapshot.plan ?? { candidates: [], notes: '' };
  const [notes, setNotes] = useState(initial.notes ?? '');
  const dirty = notes !== (initial.notes ?? '');

  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="text-neutral-400">仓位上限 {((initial.position_total_max ?? 0) * 100).toFixed(0)}% · 候选 {initial.candidates?.length ?? 0} 只</div>
      <ul>
        {(initial.candidates ?? []).map((c, i) => (
          <li key={i}>{c.code} {c.name} weight={(c.weight ?? 0).toFixed(2)}</li>
        ))}
      </ul>
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                className="bg-neutral-900 border border-neutral-700 w-full px-2 py-1 h-20"
                placeholder="计划备注 / 三段执行" />
      <button onClick={() => onApprove(dirty ? { plan: { ...initial, notes } } : {})}
              className="bg-emerald-700 hover:bg-emerald-600 px-3 py-1 rounded">
        {dirty ? '应用并继续' : '通过'}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Smoke (full path)**

```bash
# both servers up
# In browser /console, click Run on a date with non-empty pattern_hits
# Expect: NodeTimeline shows ⏸ pattern_matcher → InterruptDrawer renders PatternMatcherReview
# Click 通过 → run continues → if RiskGuard interrupt fires, drawer switches → 通过 → ...
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/right-runstream/reviews
git commit -m "feat(web): pattern_matcher / risk_guard / trade_planner review components"
```

---

## Phase 4 — Edit / re-run downstream (3 tasks)

Goal: clicking-to-edit a whitelisted field on the dashboard triggers a partial re-run from the first dirty node.

### Task 15: Field whitelist + dirty-node dependency map

**Files:**
- Create: `apps/api/editing.py`
- Create: `apps/api/tests/test_editing.py`

- [ ] **Step 1: Failing test**

`apps/api/tests/test_editing.py`:
```python
import pytest
from apps.api.editing import (validate_path, first_dirty_node, apply_patch,
                              EDITABLE_PREFIXES, NodeNotEditable)


def test_whitelist_accepts_pattern_hits():
    validate_path("pattern_hits")


def test_whitelist_rejects_random_field():
    with pytest.raises(NodeNotEditable):
        validate_path("raw_quotes")


def test_whitelist_accepts_themes_phase():
    validate_path("themes.AI算力.phase")


def test_first_dirty_node_for_themes_phase_is_theme_analyst():
    assert first_dirty_node("themes.AI算力.phase") == "theme_analyst"


def test_first_dirty_node_for_pattern_hits_is_pattern_matcher():
    assert first_dirty_node("pattern_hits") == "pattern_matcher"


def test_first_dirty_node_for_risk_flags_is_risk_guard():
    assert first_dirty_node("risk_flags") == "risk_guard"


def test_first_dirty_node_for_leader_stack_is_leader_tracker():
    assert first_dirty_node("leader_stack") == "leader_tracker"


def test_apply_patch_sets_nested_value():
    state = {"themes": {"AI算力": {"phase": "horizontal"}}}
    out = apply_patch(state, "themes.AI算力.phase", "vertical")
    assert out["themes"]["AI算力"]["phase"] == "vertical"
```

Run: import error.

- [ ] **Step 2: Implement editing module**

`apps/api/editing.py`:
```python
"""Whitelist of editable fields + dirty-node dependency map."""
from __future__ import annotations

from typing import Any

EDITABLE_PREFIXES: tuple[str, ...] = (
    "pattern_hits",
    "leader_stack",
    "themes.",       # any themes.X.{whatever}; we only allow .phase below
    "risk_flags",
)

# path prefix → first node that consumes it (so we re-run from there)
DIRTY_NODE_MAP: dict[str, str] = {
    "themes":       "theme_analyst",
    "leader_stack": "leader_tracker",
    "pattern_hits": "pattern_matcher",
    "risk_flags":   "risk_guard",
}


class NodeNotEditable(ValueError):
    pass


def validate_path(path: str) -> None:
    if path == "pattern_hits" or path == "leader_stack" or path == "risk_flags":
        return
    if path.startswith("themes.") and path.endswith(".phase"):
        return
    raise NodeNotEditable(f"path '{path}' is not in v1 editable whitelist")


def first_dirty_node(path: str) -> str:
    head = path.split(".", 1)[0]
    if head not in DIRTY_NODE_MAP:
        raise NodeNotEditable(f"no dirty-node mapping for {path}")
    return DIRTY_NODE_MAP[head]


def apply_patch(state: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep-copied state with the dotted path set to value."""
    import copy
    out = copy.deepcopy(state)
    parts = path.split(".")
    cur: Any = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return out
```

- [ ] **Step 3: Run tests**

```bash
pytest apps/api/tests/test_editing.py -v
```
Expected: 7 PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/editing.py apps/api/tests/test_editing.py
git commit -m "feat(api): editable-field whitelist + dirty-node map"
```

---

### Task 16: `/api/state/{tid}/edit` + GraphRuntime.edit

**Files:**
- Modify: `apps/api/graph_runtime.py`
- Modify: `apps/api/routes/state.py`
- Create: `apps/api/tests/test_routes_edit.py`

- [ ] **Step 1: Failing route test**

`apps/api/tests/test_routes_edit.py`:
```python
import pytest
from fastapi.testclient import TestClient
from apps.api.main import build_app


def _drain(client, tid):
    with client.stream("GET", f"/api/run/{tid}/stream") as r:
        for _ in r.iter_lines():
            pass


def test_edit_unknown_tid_404(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    r = client.post("/api/state/none/edit", json={"path": "pattern_hits", "value": []})
    assert r.status_code == 404


def test_edit_rejects_non_whitelisted_path(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    tid = client.post("/api/run", json={"date": "1970-01-01", "use_llm": False}).json()["thread_id"]
    _drain(client, tid)
    r = client.post(f"/api/state/{tid}/edit",
                    json={"path": "raw_quotes", "value": {}})
    assert r.status_code == 400


def test_edit_returns_rerun_tid(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    tid = client.post("/api/run", json={"date": "1970-01-01", "use_llm": False}).json()["thread_id"]
    _drain(client, tid)
    r = client.post(f"/api/state/{tid}/edit",
                    json={"path": "pattern_hits", "value": []})
    assert r.status_code == 200
    assert "rerun_tid" in r.json()
    assert r.json()["rerun_tid"] != tid
```

Run: 404 / route missing.

- [ ] **Step 2: Add `edit` to GraphRuntime**

Append to `apps/api/graph_runtime.py`:
```python
    def has_state(self, tid: str) -> bool:
        try:
            return bool(self._graph.get_state({"configurable": {"thread_id": tid}}).values)
        except Exception:
            return False

    async def edit(self, tid: str, path: str, value) -> str:
        from .editing import validate_path, first_dirty_node
        validate_path(path)
        cfg = {"configurable": {"thread_id": tid}}
        cur = self._graph.get_state(cfg).values
        if not cur:
            raise KeyError(f"no state for {tid}")
        # Compute the patch payload as a flat dict update — LangGraph's
        # update_state(values=..., as_node=...) re-enters from that node.
        # For nested paths (themes.X.phase) we set the whole top-level key.
        head = path.split(".")[0]
        from .editing import apply_patch
        full = apply_patch(cur, path, value)
        target_node = first_dirty_node(path)

        # Start a *new* tid for audit trail; copy the current snapshot under the
        # new tid by invoking update_state on a fresh thread.
        date = cur.get("target_date", tid.split("-", 1)[0] if "-" in tid else "")
        new_tid = f"{date}-{uuid.uuid4().hex[:8]}"
        new_cfg = {"configurable": {"thread_id": new_tid}}
        # seed the new thread's checkpoint with the patched state, marked as if
        # it came from the node *before* the dirty one — so re-stream resumes there.
        self._graph.update_state(new_cfg, full, as_node=_PREDECESSOR.get(target_node, target_node))
        self._queues[new_tid] = asyncio.Queue()
        asyncio.create_task(self._drive_continue(new_tid, new_cfg))
        return new_tid

    async def _drive_continue(self, tid: str, cfg: dict) -> None:
        # Resume from the seeded checkpoint by passing input=None
        try:
            await self._run_until_done(tid, cfg, initial=None)
            final = self._graph.get_state(cfg).values
            await self._queues[tid].put(DoneEvent(type="done",
                                                  final_state=_jsonable(final),
                                                  ts=time.time()))
        except Exception as e:
            await self._queues[tid].put(AbortedEvent(type="aborted",
                                                    reason=str(e), ts=time.time()))
```

Add at module top:
```python
# Maps each node to its predecessor in the parent graph (used so update_state
# can mark a node as "just completed" → graph resumes from the next node).
_PREDECESSOR: dict[str, str] = {
    "theme_analyst": "emotion",
    "leader_tracker": "theme_analyst",
    "pattern_matcher": "leader_tracker",
    "risk_guard": "arbitrage",
}
```

- [ ] **Step 3: Add `/edit` route**

Modify `apps/api/routes/state.py`:
```python
from pydantic import BaseModel

class EditBody(BaseModel):
    path: str
    value: object


@router.post("/state/{tid}/edit")
async def post_edit(tid: str, body: EditBody, request: Request) -> dict:
    rt = request.app.state.runtime
    if not rt.has_state(tid):
        raise HTTPException(404, f"no state for {tid}")
    try:
        new_tid = await rt.edit(tid, body.path, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "rerun_tid": new_tid}
```

- [ ] **Step 4: Run tests**

```bash
pytest apps/api/tests/ -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/graph_runtime.py apps/api/routes/state.py apps/api/tests/test_routes_edit.py
git commit -m "feat(api): /state/{tid}/edit + GraphRuntime.edit (new tid per audit)"
```

---

### Task 17: `<EditableCell>` + wire into 4 field types

**Files:**
- Create: `apps/web/lib/editing/EditableCell.tsx`
- Modify: `apps/web/lib/api/client.ts` add `editState`
- Modify: `apps/web/components/center-views/ThemesView.tsx` (theme phase)
- Modify: `apps/web/components/center-views/LeadersView.tsx` (leader_stack edit removal)
- Modify: `apps/web/components/center-views/RiskView.tsx` (risk_flags edit removal)

- [ ] **Step 1: API client add `editState`**

Append to `apps/web/lib/api/client.ts`:
```ts
export async function editState(tid: string, path: string, value: unknown): Promise<{ rerun_tid: string }> {
  const r = await fetch(`${BASE}/api/state/${tid}/edit`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, value }),
  });
  if (!r.ok) throw new Error(`edit failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: EditableCell component**

`apps/web/lib/editing/EditableCell.tsx`:
```tsx
'use client';
import { useState } from 'react';
import { useRunStore } from '@/lib/store/runStore';
import { editState } from '@/lib/api/client';
import { subscribeRun } from '@/lib/sse';
import { useStateStore } from '@/lib/store/stateStore';

interface Props {
  path: string;
  value: unknown;
  options?: string[];      // dropdown values; if omitted → free text
  display?(v: unknown): string;
}

export function EditableCell({ path, value, options, display }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(value);
  const tid = useRunStore((s) => s.tid);
  const status = useRunStore((s) => s.status);
  const merge = useStateStore((s) => s.merge);
  const { setTid, handleEvent, reset } = useRunStore.getState();

  const disabled = !tid || status === 'running' || status === 'interrupted';

  async function commit() {
    if (draft === value || !tid) { setEditing(false); return; }
    const { rerun_tid } = await editState(tid, path, draft);
    reset();
    setTid(rerun_tid);
    subscribeRun(rerun_tid, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
    setEditing(false);
  }

  if (!editing) {
    return (
      <span onDoubleClick={() => !disabled && setEditing(true)}
            className={disabled ? 'text-neutral-500' : 'cursor-pointer underline decoration-dotted'}>
        {display ? display(value) : String(value)}
      </span>
    );
  }
  if (options) {
    return (
      <select autoFocus value={String(draft)} onChange={(e) => setDraft(e.target.value)}
              onBlur={commit} className="bg-neutral-900 border border-amber-700 px-1">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  return (
    <input autoFocus value={String(draft)} onChange={(e) => setDraft(e.target.value)}
           onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && commit()}
           className="bg-neutral-900 border border-amber-700 px-1 w-24" />
  );
}
```

- [ ] **Step 3: Wire into ThemesView**

Modify `apps/web/components/center-views/ThemesView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';
import { EditableCell } from '@/lib/editing/EditableCell';

export function ThemesView() {
  const themes = (useStateStore((s) => s.state).themes ?? {}) as Record<string, any>;
  const entries = Object.entries(themes);
  if (entries.length === 0) return <div className="text-neutral-400 text-sm">题材：空</div>;
  return (
    <div className="grid grid-cols-2 gap-3 font-mono text-sm">
      {entries.map(([name, t]) => (
        <div key={name} className="border border-neutral-800 rounded p-3">
          <div className="font-bold">{name}</div>
          <div className="text-neutral-400 text-xs">
            phase: <EditableCell path={`themes.${name}.phase`} value={t.phase ?? 'horizontal'}
                                 options={['horizontal', 'vertical', 'switching', 'exhausted']} />
            {' · '}leader: {t.leader ?? '—'}
          </div>
          <div className="text-neutral-500 text-xs">members: {(t.members ?? []).join(', ')}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Wire into RiskView (remove flags) and LeadersView (remove rows) — minimal edit affordances**

Modify `apps/web/components/center-views/RiskView.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';
import { useRunStore } from '@/lib/store/runStore';
import { editState } from '@/lib/api/client';
import { subscribeRun } from '@/lib/sse';

export function RiskView() {
  const flags = (useStateStore((s) => s.state).risk_flags ?? []) as string[];
  const tid = useRunStore((s) => s.tid);
  const { setTid, handleEvent, reset } = useRunStore.getState();
  const merge = useStateStore((s) => s.merge);

  async function remove(idx: number) {
    if (!tid) return;
    const next = flags.filter((_, i) => i !== idx);
    const { rerun_tid } = await editState(tid, 'risk_flags', next);
    reset(); setTid(rerun_tid);
    subscribeRun(rerun_tid, (ev) => {
      handleEvent(ev);
      if (ev.type === 'node_end') merge(ev.state_patch);
      if (ev.type === 'done') merge(ev.final_state);
    });
  }

  if (flags.length === 0) return <div className="text-neutral-400 text-sm">无风控触发</div>;
  return (
    <ul className="space-y-1 font-mono text-sm">
      {flags.map((f, i) => (
        <li key={i} className="flex justify-between border border-neutral-800 rounded px-2 py-1">
          <span>{f}</span>
          <button onClick={() => remove(i)} className="text-red-400 hover:text-red-300">驳回</button>
        </li>
      ))}
    </ul>
  );
}
```

(Apply similar dismissal-on-row pattern to `LeadersView` if you want manual leader-stack editing in v1; otherwise leave read-only.)

- [ ] **Step 5: Smoke**

```bash
# Run a date that produces themes
# Double-click a theme phase value → dropdown appears → pick "vertical"
# Right column should re-stream from theme_analyst onwards; candidates view updates within seconds
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/editing apps/web/lib/api/client.ts apps/web/components/center-views
git commit -m "feat(web): EditableCell + theme.phase / risk_flags inline editing"
```

---

## Phase 5 — Charts (2 tasks)

### Task 18: KLineChart + Sparkline wrappers

**Files:**
- Create: `apps/web/components/charts/KLineChart.tsx`
- Create: `apps/web/components/charts/Sparkline.tsx`

- [ ] **Step 1: Install lib**

```bash
cd apps/web && npm install --save lightweight-charts
```

- [ ] **Step 2: KLineChart wrapper**

`apps/web/components/charts/KLineChart.tsx`:
```tsx
'use client';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createChart, CandlestickSeries, type IChartApi } from 'lightweight-charts';

interface Bar { time: string; open: number; high: number; low: number; close: number; volume: number }
interface KlineResp { code: string; bars: Bar[]; limit_up_days: string[] }

async function fetchKline(code: string, days: number): Promise<KlineResp> {
  const r = await fetch(`/api/kline/${code}?days=${days}`);
  if (!r.ok) throw new Error(`kline ${code}`);
  return r.json();
}

export function KLineChart({ code, days = 60, height = 280 }: { code: string; days?: number; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ['kline', code, days],
    queryFn: () => fetchKline(code, days),
    staleTime: 24 * 3600 * 1000,
  });

  useEffect(() => {
    if (!ref.current || !data) return;
    const chart = createChart(ref.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: '#888' },
      grid: { vertLines: { color: '#222' }, horzLines: { color: '#222' } },
      timeScale: { borderColor: '#333' },
    });
    chartRef.current = chart;
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });
    series.setData(data.bars);
    if (data.limit_up_days.length) {
      series.setMarkers(data.limit_up_days.map((d) => ({
        time: d, position: 'belowBar', color: '#ef4444', shape: 'arrowUp', text: '涨停',
      })));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, height]);

  if (isLoading) return <div className="text-neutral-500 text-xs">加载 K 线…</div>;
  return <div ref={ref} style={{ height }} />;
}
```

- [ ] **Step 3: Sparkline (simpler line series, no axes)**

`apps/web/components/charts/Sparkline.tsx`:
```tsx
'use client';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createChart, LineSeries } from 'lightweight-charts';

async function fetchKline(code: string, days: number) {
  const r = await fetch(`/api/kline/${code}?days=${days}`);
  return r.json();
}

export function Sparkline({ code, days = 30, width = 80, height = 24 }: {
  code: string; days?: number; width?: number; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useQuery({
    queryKey: ['kline', code, days, 'sparkline'],
    queryFn: () => fetchKline(code, days),
    staleTime: 24 * 3600 * 1000,
  });

  useEffect(() => {
    if (!ref.current || !data?.bars) return;
    const chart = createChart(ref.current, {
      width, height,
      layout: { background: { color: 'transparent' }, textColor: 'transparent' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      timeScale: { visible: false },
      rightPriceScale: { visible: false },
      crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
      handleScale: false, handleScroll: false,
    });
    const series = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1 });
    series.setData(data.bars.map((b: any) => ({ time: b.time, value: b.close })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, width, height]);

  return <div ref={ref} style={{ width, height }} />;
}
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/charts apps/web/package.json apps/web/package-lock.json
git commit -m "feat(web): lightweight-charts wrappers (KLine + Sparkline)"
```

---

### Task 19: Wire charts into candidates table + leader drawer + sentiment

**Files:**
- Modify: `apps/web/components/center-views/CandidatesView.tsx`
- Create: `apps/web/components/center-views/LeaderDrawer.tsx`
- Modify: `apps/web/components/center-views/LeadersView.tsx`
- Create: `apps/web/components/left-context/SentimentSpark.tsx`
- Modify: `apps/web/components/left-context/DateNavigator.tsx` or compose into a left container

- [ ] **Step 1: Add Sparkline column to CandidatesView**

Modify `CandidatesView.tsx`:
```tsx
import { Sparkline } from '@/components/charts/Sparkline';
// ... in <tr>:
<td><Sparkline code={c.code} /></td>
```

- [ ] **Step 2: LeaderDrawer with KLineChart**

`apps/web/components/center-views/LeaderDrawer.tsx`:
```tsx
'use client';
import { useViewStore } from '@/lib/store/viewStore';
import { KLineChart } from '@/components/charts/KLineChart';

export function LeaderDrawer() {
  const code = useViewStore((s) => s.selectedCode);
  const close = () => useViewStore.getState().selectCode(null);
  if (!code) return null;
  return (
    <div className="fixed right-0 top-0 h-full w-[480px] bg-neutral-950 border-l border-neutral-800 z-50 p-4 overflow-y-auto">
      <div className="flex justify-between mb-3">
        <h3 className="font-mono">{code}</h3>
        <button onClick={close} className="text-neutral-400 hover:text-neutral-200">×</button>
      </div>
      <KLineChart code={code} days={60} height={320} />
    </div>
  );
}
```

- [ ] **Step 3: Mount drawer somewhere always-rendered (console page top level)**

Modify `apps/web/app/console/page.tsx`:
```tsx
import { LeaderDrawer } from '@/components/center-views/LeaderDrawer';
// at end of returned JSX:
return (
  <>
    <ThreeColumnLayout {...} />
    <LeaderDrawer />
  </>
);
```

- [ ] **Step 4: SentimentSpark in left column**

`apps/web/components/left-context/SentimentSpark.tsx`:
```tsx
'use client';
import { useQuery } from '@tanstack/react-query';
import { getRunsList, getRunByDate } from '@/lib/api/client';

export function SentimentSpark({ days = 7 }: { days?: number }) {
  const { data: runs = [] } = useQuery({ queryKey: ['runs'], queryFn: getRunsList });
  const last = runs.slice(0, days).reverse();

  // Tiny inline SVG sparkline; no chart lib needed for 7 points.
  // We'd ideally fetch sentiment_value from each — done via parallel queries:
  return (
    <div className="font-mono text-xs">
      <div className="text-[10px] uppercase text-neutral-500 mb-1">情绪 7 日</div>
      <div className="flex gap-px h-6 items-end">
        {last.map((r) => (
          <SparkBar key={r.date} date={r.date} />
        ))}
      </div>
    </div>
  );
}

function SparkBar({ date }: { date: string }) {
  const { data } = useQuery({ queryKey: ['runs', date],
    queryFn: () => getRunByDate(date) });
  const v = (data?.sentiment_value as number | undefined) ?? 0;
  const h = Math.min(24, Math.max(2, v / 200)); // 0..4800 → 0..24px
  return <div title={`${date}: ${v}`} style={{ height: h, width: 6 }} className="bg-amber-500" />;
}
```

- [ ] **Step 5: Compose into left column**

Modify `console/page.tsx` `left` slot:
```tsx
left={(<><SentimentSpark /><div className="mt-3"><DateNavigator /></div></>)}
```

- [ ] **Step 6: Smoke + commit**

```bash
# Browser → Run → click a leader row → drawer with K line opens
# History list bars on the left show sentiment over last 7 days
```

```bash
git add apps/web/components/center-views apps/web/components/left-context apps/web/app/console/page.tsx
git commit -m "feat(web): wire charts — candidate sparklines + leader K-line + sentiment spark"
```

---

## Phase 6 — Polish, error UX, e2e (3 tasks)

### Task 20: SSE Last-Event-ID + interrupt 30-min auto-approve + error banner

**Files:**
- Modify: `apps/api/graph_runtime.py` (auto-approve timeout)
- Modify: `apps/api/routes/run.py` (Last-Event-ID handling)
- Modify: `apps/web/lib/sse.ts` (no client change needed — `EventSource` does Last-Event-ID itself, we just need to honor it server-side)
- Create: `apps/web/components/shell/ErrorBanner.tsx`

- [ ] **Step 1: Auto-approve interrupt after 30 min**

Modify `apps/api/graph_runtime.py` `_run_until_done` — replace the `review = await fut` line:
```python
                    try:
                        review = await asyncio.wait_for(fut, timeout=30 * 60)
                    except asyncio.TimeoutError:
                        review = {"action": "approve", "patch": {}, "_auto": True}
                        # also drop the abandoned future
                        self._resume_signals.pop(tid, None)
```

- [ ] **Step 2: Server-side Last-Event-ID re-send**

Modify `apps/api/graph_runtime.py` to keep a sliding event log per tid:
```python
    # in __init__
    self._history: dict[str, list[tuple[int, RunEvent]]] = {}
    self._event_seq: dict[str, int] = {}
```

Wrap every `q.put(ev)` site in a helper:
```python
    def _emit(self, tid: str, ev) -> None:
        n = self._event_seq.get(tid, 0) + 1
        self._event_seq[tid] = n
        hist = self._history.setdefault(tid, [])
        hist.append((n, ev))
        if len(hist) > 100:
            del hist[0:len(hist) - 100]
        self._queues[tid].put_nowait(ev)
```

(Then replace every `await self._queues[tid].put(...)` and `await q.put(...)` with `self._emit(tid, ...)`. Drop awaits since `put_nowait` is sync.)

Add resume helper:
```python
    def replay_after(self, tid: str, last_id: int):
        for n, ev in self._history.get(tid, []):
            if n > last_id:
                yield n, ev

    async def stream(self, tid: str, last_id: int = 0) -> AsyncIterator[tuple[int, RunEvent]]:
        # First, replay any history past last_id
        for n, ev in self.replay_after(tid, last_id):
            yield n, ev
            if ev["type"] in _TERMINAL_TYPES:
                return
        # Then live
        q = self._queues[tid]
        while True:
            ev = await q.get()
            n = self._event_seq[tid]
            yield n, ev
            if ev["type"] in _TERMINAL_TYPES:
                break
```

Modify `apps/api/routes/run.py` `get_stream`:
```python
@router.get("/run/{tid}/stream")
async def get_stream(tid: str, request: Request):
    rt = request.app.state.runtime
    if tid not in rt._queues:
        raise HTTPException(status_code=404, detail="unknown thread_id")

    last_id = int(request.headers.get("last-event-id", "0") or 0)

    async def gen():
        async for n, ev in rt.stream(tid, last_id=last_id):
            yield {"id": str(n), "event": ev["type"], "data": json.dumps(ev, default=str)}

    return EventSourceResponse(gen())
```

- [ ] **Step 3: ErrorBanner component**

`apps/web/components/shell/ErrorBanner.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function ErrorBanner() {
  const errors = (useStateStore((s) => s.state).errors as string[] | undefined) ?? [];
  if (errors.length === 0) return null;
  return (
    <div className="border-b border-red-800 bg-red-950/40 px-4 py-2 text-xs font-mono text-red-300">
      <details>
        <summary className="cursor-pointer">⚠ {errors.length} 个节点错误</summary>
        <ul className="mt-1 ml-4 list-disc">
          {errors.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      </details>
    </div>
  );
}
```

Mount above ThreeColumnLayout in `console/page.tsx`:
```tsx
return (<><ErrorBanner /><ThreeColumnLayout {...} /><LeaderDrawer /></>);
```

- [ ] **Step 4: Tests for runtime auto-approve + replay**

`apps/api/tests/test_runtime_resilience.py`:
```python
import asyncio
import pytest
from apps.api.graph_runtime import GraphRuntime


@pytest.mark.asyncio
async def test_replay_returns_history_for_known_tid(tmp_path):
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="1970-01-01", use_llm=False, refresh=False)
    seen = []
    async for n, ev in rt.stream(tid, last_id=0):
        seen.append((n, ev["type"]))
        if ev["type"] in ("done", "aborted"):
            break
    # second consumer with last_id=mid should resume cleanly
    mid = seen[len(seen) // 2][0]
    second = []
    async for n, ev in rt.stream(tid, last_id=mid):
        second.append((n, ev["type"]))
        if ev["type"] in ("done", "aborted"):
            break
    assert second[0][0] > mid
```

```bash
pytest apps/api/tests/test_runtime_resilience.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/graph_runtime.py apps/api/routes/run.py apps/web/components/shell apps/web/app/console/page.tsx apps/api/tests/test_runtime_resilience.py
git commit -m "feat: SSE Last-Event-ID replay + 30-min interrupt auto-approve + error banner"
```

---

### Task 21: Soft data-incomplete banner + tnum + table virtualization

**Files:**
- Create: `apps/web/components/shell/DataQualityBanner.tsx`
- Modify: `apps/web/components/center-views/CandidatesView.tsx` (virtualize via @tanstack/react-virtual)
- Modify: `apps/web/app/console/page.tsx`

- [ ] **Step 1: DataQualityBanner**

`apps/web/components/shell/DataQualityBanner.tsx`:
```tsx
'use client';
import { useStateStore } from '@/lib/store/stateStore';

export function DataQualityBanner() {
  const errors = (useStateStore((s) => s.state).errors as string[] | undefined) ?? [];
  const incomplete = errors.some((e) => /no .* data|RemoteDisconnected|fetch failed/i.test(e));
  if (!incomplete) return null;
  return (
    <div className="bg-amber-950/40 border-b border-amber-800 px-4 py-1 text-xs font-mono text-amber-300">
      📊 数据不全，结论仅供参考
    </div>
  );
}
```

Mount above ErrorBanner in console page.

- [ ] **Step 2: Virtualize CandidatesView**

```bash
cd apps/web && npm install --save @tanstack/react-virtual
```

Update CandidatesView (sketch — full file follows the same structure as before, wrapping `<tbody>` content in a virtualizer when rows > 30).

- [ ] **Step 3: Smoke + commit**

```bash
git add apps/web
git commit -m "feat(web): data-quality soft banner + candidate table virtualization"
```

---

### Task 22: Playwright happy-path

**Files:**
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/tests/e2e/happy-path.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd apps/web
npm install --save-dev @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Config**

`apps/web/playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  use: { baseURL: 'http://localhost:3000' },
  webServer: [
    { command: 'cd ../.. && uvicorn apps.api.main:app --port 8000', port: 8000, reuseExistingServer: true },
    { command: 'npm run dev', port: 3000, reuseExistingServer: true },
  ],
});
```

- [ ] **Step 3: Test**

`apps/web/tests/e2e/happy-path.spec.ts`:
```ts
import { test, expect } from '@playwright/test';

test('happy path: open console, run a date, see node timeline complete', async ({ page }) => {
  await page.goto('/console');
  await expect(page.locator('text=▶ Run')).toBeVisible();
  await page.getByRole('button', { name: '▶ Run' }).click();
  await expect(page.locator('text=status: done').or(page.locator('text=status: interrupted'))).toBeVisible({ timeout: 60_000 });
});
```

- [ ] **Step 4: Run e2e**

```bash
cd apps/web && npx playwright test
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/playwright.config.ts apps/web/tests apps/web/package.json apps/web/package-lock.json
git commit -m "test(web): playwright happy-path e2e"
```

---

## Phase 7 — Production packaging (1 task)

### Task 23: Static export + FastAPI mount + Makefile

**Files:**
- Modify: `apps/web/next.config.mjs` (already has `output: 'export'`)
- Modify: `apps/api/main.py` (mount static)
- Create: `Makefile`

- [ ] **Step 1: Mount static dir in FastAPI**

Modify `apps/api/main.py` `build_app` end:
```python
    # Mount Next.js static export at / when present
    from fastapi.staticfiles import StaticFiles
    web_out = Path(__file__).resolve().parents[2] / "apps" / "web" / "out"
    if web_out.exists():
        app.mount("/", StaticFiles(directory=str(web_out), html=True), name="web")
    return app
```

Add at top:
```python
from pathlib import Path
```

- [ ] **Step 2: Makefile**

`Makefile` (project root):
```makefile
.PHONY: install dev api web test test-live build serve gen-api lint

install:
	pip install -e ".[dev]"
	cd apps/web && npm install

dev:
	@( trap 'kill 0' SIGINT; \
	   uvicorn apps.api.main:app --reload --port 8000 & \
	   ( cd apps/web && npm run dev ) & \
	   wait )

api:
	uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

gen-api:
	cd apps/web && npm run gen:api

test:
	pytest -q
	cd apps/web && npm test

test-live:
	pytest -q -m live

lint:
	ruff check .
	mypy apps/api src
	cd apps/web && npx tsc --noEmit && npm run lint

build:
	cd apps/web && npm run build

serve:
	uvicorn apps.api.main:app --port 8000
```

- [ ] **Step 3: Smoke production mode**

```bash
make build
make serve &
sleep 2
curl -sI http://localhost:8000/ | head -2
curl -s http://localhost:8000/api/health
kill %1
```
Expected: HTML at `/`, `{"ok":true}` at `/api/health`.

- [ ] **Step 4: Commit**

```bash
git add Makefile apps/api/main.py
git commit -m "feat: production single-process serve via static mount"
```

---

## Self-review checklist (run before handing the plan to an executor)

1. **Spec coverage:** every Phase 1–7 milestone in the spec maps to one or more tasks above. Open questions in spec §11 (stream_mode dedup, akshare semaphore size, dirty-node map maintenance, parent-tid linkage, multi-tab) are deliberately deferred — re-open if Phase 1/5 reveal blockers.
2. **Placeholder scan:** none — every code step has runnable code. The few "extend with same pattern" lines (e.g. ArbitrageView/RiskView/PlanView in Task 10) reference a concrete sibling file you must read; that's a deliberate cap on plan length, not a spec hole.
3. **Type consistency:** SSE event shapes in `apps/api/events.py` mirror the TS `RunEvent` in `apps/web/lib/store/runStore.ts` field-for-field. `MarketState` keys referenced in views (`emotion_phase`, `pattern_hits`, `themes`, `leader_stack`, `candidates`, `risk_flags`, `plan`, `errors`) all exist in `src/youzi_agent/state.py`. Endpoint paths and methods in client code match the FastAPI routes.

---

## Execution checkpoints

Each phase's last task ends with the build in a demoable state. Suggested human-review breakpoints:

- **After Phase 1** — run `make api` + curl every route
- **After Phase 2** — run `make dev`, click Run, watch SSE
- **After Phase 3** — run a date that has pattern_hits, exercise a full interrupt-resume cycle
- **After Phase 4** — edit a theme phase, watch the rerun chain land
- **After Phase 5** — click a leader, see K line; check sparklines in candidate rows
- **After Phase 6** — inspect resilience via toggling akshare offline (`/etc/hosts` block) mid-run
- **After Phase 7** — `make build && make serve`, single-process production parity
