import asyncio
import pytest
from apps.api.graph_runtime import GraphRuntime


@pytest.mark.asyncio
async def test_replay_returns_history_for_known_tid(tmp_path):
    rt = GraphRuntime(checkpoint_path=str(tmp_path / "ckpt.db"))
    tid = await rt.start(date="1970-01-01", use_llm=False, refresh=False)
    seen: list[tuple[int, str]] = []
    async for n, ev in rt.stream(tid, last_id=0):
        seen.append((n, ev["type"]))
        if ev["type"] in ("done", "aborted"):
            break
    assert len(seen) > 1
    mid = seen[len(seen) // 2][0]
    second: list[tuple[int, str]] = []
    async for n, ev in rt.stream(tid, last_id=mid):
        second.append((n, ev["type"]))
        if ev["type"] in ("done", "aborted"):
            break
    # All events in second consumer have id > mid
    assert all(n > mid for n, _ in second)
    assert second[-1][1] in ("done", "aborted")
