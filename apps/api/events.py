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
