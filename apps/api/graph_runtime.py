"""Wraps youzi_agent graph in an async-friendly runtime with per-thread queues."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any, AsyncIterator

from langgraph.types import Command

from youzi_agent.graph import build_graph

from .events import (AbortedEvent, DoneEvent, InterruptEvent, NodeEndEvent,
                     NodeErrorEvent, NodeStartEvent, RunEvent)

_TERMINAL_TYPES = {"done", "aborted"}


class GraphRuntime:
    def __init__(self, checkpoint_path: str = "checkpoints.db") -> None:
        self._graph = build_graph(checkpoint_path=checkpoint_path)
        self._queues: dict[str, asyncio.Queue[RunEvent]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._resume_signals: dict[str, asyncio.Future] = {}

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

    async def resume(self, tid: str, payload: dict) -> None:
        """Deliver a human-review payload to the pending interrupt for `tid`."""
        fut = self._resume_signals.pop(tid, None)
        if fut is None:
            raise RuntimeError(f"no pending interrupt for {tid}")
        fut.set_result(payload)

    async def _drive(self, tid: str, date: str, use_llm: bool, refresh: bool) -> None:
        cfg = {"configurable": {"thread_id": tid}}
        q = self._queues[tid]
        loop = asyncio.get_running_loop()
        last_node: dict[str, str | None] = {"v": None}

        def _put_threadsafe(ev: RunEvent) -> None:
            asyncio.run_coroutine_threadsafe(q.put(ev), loop).result()

        def _run_sync(initial: Any) -> dict | None:
            """Run graph (or resume from checkpoint when `initial` is a Command)
            until either an interrupt or completion.

            Returns the interrupt payload (the dict the node passed to
            `interrupt()`) when paused, else None on natural completion.
            """
            for chunk in self._graph.stream(initial, config=cfg, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    iv = chunk["__interrupt__"]
                    first = iv[0] if isinstance(iv, (tuple, list)) else iv
                    return first.value
                for node, patch in chunk.items():
                    if last_node["v"] != node:
                        _put_threadsafe(NodeStartEvent(
                            type="node_start", node=node, ts=time.time()))
                        last_node["v"] = node
                    _put_threadsafe(NodeEndEvent(
                        type="node_end", node=node, ts=time.time(),
                        state_patch=_jsonable(patch),
                    ))
            return None

        try:
            await q.put(NodeStartEvent(type="node_start", node="<run>", ts=time.time()))
            cur_input: Any = {"target_date": date, "use_llm": use_llm}
            while True:
                interrupt_payload = await asyncio.to_thread(_run_sync, cur_input)
                if interrupt_payload is None:
                    break
                # Surface the interrupt to the SSE stream.
                node_name = "<unknown>"
                snapshot: dict[str, Any] = {}
                if isinstance(interrupt_payload, dict):
                    node_name = interrupt_payload.get("node", "<unknown>")
                    snapshot = interrupt_payload.get("snapshot", {}) or {}
                await q.put(InterruptEvent(
                    type="interrupt",
                    node=node_name,
                    snapshot=_jsonable(snapshot),
                    ts=time.time(),
                ))
                fut = loop.create_future()
                self._resume_signals[tid] = fut
                review = await fut
                # Optional explicit state patch on resume.
                if isinstance(review, dict) and review.get("patch"):
                    self._graph.update_state(cfg, review["patch"])
                # Deliver the review dict back to the suspended interrupt() call.
                cur_input = Command(resume=review)
            final = self._graph.get_state(cfg).values
            await q.put(DoneEvent(type="done", final_state=_jsonable(final), ts=time.time()))
        except Exception as e:
            await q.put(NodeErrorEvent(type="node_error", node=last_node["v"] or "<run>",
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
