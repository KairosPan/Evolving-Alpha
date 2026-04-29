import asyncio
import pytest

from apps.api.graph_runtime import GraphRuntime


@pytest.mark.no_auto_resume
@pytest.mark.asyncio
async def test_interrupt_then_resume_completes(tmp_path):
    """Without YOUZI_AUTO_RESUME, the graph nodes call `interrupt(...)`. The
    runtime must surface an InterruptEvent on the SSE stream and await an
    out-of-band resume() call before the graph proceeds to terminal."""
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="1970-01-01", use_llm=False, refresh=False)

    interrupted = False

    async def consume():
        nonlocal interrupted
        async for ev in rt.stream(tid):
            if ev["type"] == "interrupt":
                interrupted = True
                await rt.resume(tid, {"action": "approve", "patch": {}})
            if ev["type"] in ("done", "aborted"):
                return ev
        return None

    final = await asyncio.wait_for(consume(), timeout=60)
    assert interrupted, "expected at least one interrupt during run"
    assert final is not None
    assert final["type"] in ("done", "aborted")
