import httpx
import pytest
from fastapi.testclient import TestClient
from apps.api.main import build_app


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """sse_starlette caches AppStatus.should_exit_event in a module-level
    singleton bound to the first loop that touched it, which breaks pytest
    re-creating loops per test. Reset it before each test."""
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield


def test_edit_unknown_tid_404(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    r = client.post("/api/state/none/edit", json={"path": "pattern_hits", "value": []})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_edit_rejects_non_whitelisted_path(tmp_path):
    app = build_app(checkpoint_path=str(tmp_path / "ckpt.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        r = await client.post("/api/run", json={"date": "1970-01-01", "use_llm": False})
        tid = r.json()["thread_id"]
        async with client.stream("GET", f"/api/run/{tid}/stream") as resp:
            async for _ in resp.aiter_lines():
                pass
        r = await client.post(f"/api/state/{tid}/edit",
                              json={"path": "raw_quotes", "value": {}})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_edit_returns_rerun_tid(tmp_path):
    app = build_app(checkpoint_path=str(tmp_path / "ckpt.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        r = await client.post("/api/run", json={"date": "1970-01-01", "use_llm": False})
        tid = r.json()["thread_id"]
        async with client.stream("GET", f"/api/run/{tid}/stream") as resp:
            async for _ in resp.aiter_lines():
                pass
        r = await client.post(f"/api/state/{tid}/edit",
                              json={"path": "pattern_hits", "value": []})
    assert r.status_code == 200
    body = r.json()
    assert "rerun_tid" in body
    assert body["rerun_tid"] != tid
