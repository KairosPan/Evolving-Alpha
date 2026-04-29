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

_PREDECESSOR: dict[str, str] = {
    "theme_analyst": "emotion",
    "leader_tracker": "theme_analyst",
    "pattern_matcher": "leader_tracker",
    "risk_guard": "arbitrage",
}


class GraphRuntime:
    def __init__(self, checkpoint_path: str = "checkpoints.db") -> None:
        self._graph = build_graph(checkpoint_path=checkpoint_path)
        self._queues: dict[str, asyncio.Queue[RunEvent]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._resume_signals: dict[str, asyncio.Future] = {}
        self._history: dict[str, list[tuple[int, RunEvent]]] = {}
        self._event_seq: dict[str, int] = {}

    def _record(self, tid: str, ev: RunEvent) -> int:
        """Record event in history; return its sequence id.

        Sync-only (dict updates). Safe to call from any thread for our
        single-user case; if concurrent runs ever cause a race on
        `_event_seq`, wrap with a `threading.Lock`.
        """
        n = self._event_seq.get(tid, 0) + 1
        self._event_seq[tid] = n
        hist = self._history.setdefault(tid, [])
        hist.append((n, ev))
        if len(hist) > 100:
            del hist[0:len(hist) - 100]
        return n

    async def start(self, *, date: str, use_llm: bool, refresh: bool) -> str:
        if refresh:
            os.environ["YOUZI_REFRESH"] = "1"
        tid = f"{date}-{uuid.uuid4().hex[:8]}"
        self._queues[tid] = asyncio.Queue()
        # Retain the task ref so the event loop keeps it alive until done.
        self._tasks[tid] = asyncio.create_task(self._drive(tid, date, use_llm, refresh))
        return tid

    async def stream(self, tid: str, last_id: int = 0) -> AsyncIterator[tuple[int, RunEvent]]:
        # Replay history past last_id first
        for n, ev in self._history.get(tid, []):
            if n > last_id:
                yield n, ev
                if ev["type"] in _TERMINAL_TYPES:
                    return
        # Then live
        q = self._queues[tid]
        while True:
            ev = await q.get()
            n = self._event_seq.get(tid, 0)
            yield n, ev
            if ev["type"] in _TERMINAL_TYPES:
                break

    async def resume(self, tid: str, payload: dict) -> None:
        """Deliver a human-review payload to the pending interrupt for `tid`."""
        fut = self._resume_signals.pop(tid, None)
        if fut is None:
            raise RuntimeError(f"no pending interrupt for {tid}")
        fut.set_result(payload)

    def has_state(self, tid: str) -> bool:
        try:
            return bool(self._graph.get_state({"configurable": {"thread_id": tid}}).values)
        except Exception:
            return False

    async def edit(self, tid: str, path: str, value: Any) -> str:
        from .editing import apply_patch, first_dirty_node, validate_path
        validate_path(path)
        cfg = {"configurable": {"thread_id": tid}}
        cur = self._graph.get_state(cfg).values
        if not cur:
            raise KeyError(f"no state for {tid}")
        full = apply_patch(cur, path, value)
        target_node = first_dirty_node(path)

        date = cur.get("target_date") or (tid.split("-", 1)[0] if "-" in tid else "")
        new_tid = f"{date}-{uuid.uuid4().hex[:8]}"
        new_cfg = {"configurable": {"thread_id": new_tid}}
        as_node = _PREDECESSOR.get(target_node, target_node)
        self._graph.update_state(new_cfg, full, as_node=as_node)
        self._queues[new_tid] = asyncio.Queue()
        self._tasks[new_tid] = asyncio.create_task(self._drive_continue(new_tid, new_cfg))
        return new_tid

    async def _drive_continue(self, tid: str, cfg: dict) -> None:
        """Resume a fresh tid from a seeded checkpoint until done/interrupt."""
        q = self._queues[tid]
        loop = asyncio.get_running_loop()
        last_node: dict[str, str | None] = {"v": None}

        def _put_threadsafe(ev: RunEvent) -> None:
            self._record(tid, ev)
            asyncio.run_coroutine_threadsafe(q.put(ev), loop).result()

        async def _emit(ev: RunEvent) -> None:
            self._record(tid, ev)
            await q.put(ev)

        def _run_sync(initial: Any) -> dict | None:
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
            cur_input: Any = None
            while True:
                interrupt_payload = await asyncio.to_thread(_run_sync, cur_input)
                if interrupt_payload is None:
                    break
                node_name = "<unknown>"
                snapshot: dict[str, Any] = {}
                if isinstance(interrupt_payload, dict):
                    node_name = interrupt_payload.get("node", "<unknown>")
                    snapshot = interrupt_payload.get("snapshot", {}) or {}
                await _emit(InterruptEvent(
                    type="interrupt",
                    node=node_name,
                    snapshot=_jsonable(snapshot),
                    ts=time.time(),
                ))
                fut = loop.create_future()
                self._resume_signals[tid] = fut
                try:
                    review = await asyncio.wait_for(fut, timeout=30 * 60)
                except asyncio.TimeoutError:
                    review = {"action": "approve", "patch": {}, "_auto": True}
                    self._resume_signals.pop(tid, None)
                if isinstance(review, dict) and review.get("patch"):
                    self._graph.update_state(cfg, review["patch"])
                cur_input = Command(resume=review)
            final = self._graph.get_state(cfg).values
            await _emit(DoneEvent(type="done", final_state=_jsonable(final), ts=time.time()))
        except Exception as e:
            await _emit(NodeErrorEvent(type="node_error", node=last_node["v"] or "<run>",
                                       ts=time.time(), message=str(e)))
            await _emit(AbortedEvent(type="aborted", reason=str(e), ts=time.time()))

    async def _drive(self, tid: str, date: str, use_llm: bool, refresh: bool) -> None:
        cfg = {"configurable": {"thread_id": tid}}
        q = self._queues[tid]
        loop = asyncio.get_running_loop()
        last_node: dict[str, str | None] = {"v": None}

        def _put_threadsafe(ev: RunEvent) -> None:
            self._record(tid, ev)
            asyncio.run_coroutine_threadsafe(q.put(ev), loop).result()

        async def _emit(ev: RunEvent) -> None:
            self._record(tid, ev)
            await q.put(ev)

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
            await _emit(NodeStartEvent(type="node_start", node="<run>", ts=time.time()))
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
                await _emit(InterruptEvent(
                    type="interrupt",
                    node=node_name,
                    snapshot=_jsonable(snapshot),
                    ts=time.time(),
                ))
                fut = loop.create_future()
                self._resume_signals[tid] = fut
                try:
                    review = await asyncio.wait_for(fut, timeout=30 * 60)
                except asyncio.TimeoutError:
                    review = {"action": "approve", "patch": {}, "_auto": True}
                    self._resume_signals.pop(tid, None)
                # Optional explicit state patch on resume.
                if isinstance(review, dict) and review.get("patch"):
                    self._graph.update_state(cfg, review["patch"])
                # Deliver the review dict back to the suspended interrupt() call.
                cur_input = Command(resume=review)
            final = self._graph.get_state(cfg).values
            await _emit(DoneEvent(type="done", final_state=_jsonable(final), ts=time.time()))
        except Exception as e:
            await _emit(NodeErrorEvent(type="node_error", node=last_node["v"] or "<run>",
                                       ts=time.time(), message=str(e)))
            await _emit(AbortedEvent(type="aborted", reason=str(e), ts=time.time()))


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
