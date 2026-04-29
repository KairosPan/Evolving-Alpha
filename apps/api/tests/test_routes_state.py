import httpx
import pytest
from fastapi.testclient import TestClient
from apps.api.main import build_app


def test_get_state_unknown_tid_404(tmp_path):
    client = TestClient(build_app(checkpoint_path=str(tmp_path / "ckpt.db")))
    assert client.get("/api/state/does-not-exist").status_code == 404


@pytest.mark.asyncio
async def test_get_state_after_run(tmp_path):
    app = build_app(checkpoint_path=str(tmp_path / "ckpt.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        r = await client.post("/api/run", json={"date": "1970-01-01", "use_llm": False})
        tid = r.json()["thread_id"]
        # drain stream so graph completes
        async with client.stream("GET", f"/api/run/{tid}/stream") as resp:
            async for _ in resp.aiter_lines():
                pass
        r = await client.get(f"/api/state/{tid}")
    assert r.status_code == 200
    assert "target_date" in r.json()
