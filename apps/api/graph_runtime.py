"""Wraps youzi_agent graph in an async-friendly runtime with per-thread queues."""
from __future__ import annotations

import asyncio
import json
import os
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
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, *, date: str, use_llm: bool, refresh: bool) -> str:
        if refresh:
            os.environ["YOUZI_REFRESH"] = "1"
        tid = f"{date}-{uuid.uuid4().hex[:8]}"
        self._queues[tid] = asyncio.Queue()
        # Retain the task ref so the event loop keeps it alive until done.
        self._tasks[tid] = asyncio.create_task(self._drive(tid, date, use_llm, refresh))
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
