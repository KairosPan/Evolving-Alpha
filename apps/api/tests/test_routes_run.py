import httpx
import pytest

from apps.api.main import build_app


@pytest.mark.asyncio
async def test_post_run_returns_thread_id(tmp_path):
    """Sync TestClient is fine for non-streaming POST."""
    app = build_app(checkpoint_path=str(tmp_path / "ckpt.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/run", json={"date": "2026-04-26", "use_llm": False})
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"].startswith("2026-04-26-")


@pytest.mark.asyncio
async def test_stream_yields_done_event(tmp_path):
    """SSE stream must use AsyncClient — TestClient's per-call portal loops
    deadlock against the asyncio.Queue created in POST."""
    app = build_app(checkpoint_path=str(tmp_path / "ckpt.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        r = await client.post("/api/run", json={"date": "1970-01-01", "use_llm": False})
        tid = r.json()["thread_id"]
        types: list[str] = []
        async with client.stream("GET", f"/api/run/{tid}/stream") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    types.append(line.split(":", 1)[1].strip())
                if "done" in types or "aborted" in types:
                    break
        assert types and types[-1] in ("done", "aborted")
