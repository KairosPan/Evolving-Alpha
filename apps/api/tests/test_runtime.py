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
    async for n, ev in rt.stream(tid):
        events.append(ev)
        if len(events) > 200:
            pytest.fail("stream did not terminate")

    types = {e["type"] for e in events}
    assert "node_start" in types
    assert types & {"done", "aborted"}, f"no terminal event in {types}"
