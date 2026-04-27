"""Parent graph: SENSE -> ANALYZE -> DECIDE."""
from __future__ import annotations

import pickle
import sqlite3
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes.arbitrage import arbitrage_node
from .nodes.cycle_switch import cycle_switch_node
from .nodes.emotion import emotion_node
from .nodes.index_cycle import index_cycle_node
from .nodes.leader_tracker import leader_tracker_node
from .nodes.market_sensor import market_sensor_node
from .nodes.pattern_matcher import pattern_matcher_node
from .nodes.post_mortem import post_mortem_node
from .nodes.risk_guard import risk_guard_node
from .nodes.theme_analyst import theme_analyst_node
from .nodes.trade_planner import trade_planner_node
from .state import MarketState
from .subagents.continuous import build_con_subgraph
from .subagents.first_board import build_fb_subgraph
from .subagents.setback_reversal import build_sr_subgraph
from .subagents.weak_to_strong import build_w2s_subgraph

SUBAGENT_NAMES = ["weak_to_strong", "first_board", "continuous", "setback_reversal"]


def _df_to_jsonable(obj: Any) -> Any:
    """Recursively convert pandas DataFrames inside dicts/lists to JSON-able forms.

    The SqliteSaver uses a separate `jsonplus_serde` (JSON-only, no pickle path)
    to write checkpoint metadata, which captures node-level `writes`. Since our
    `state['raw']` carries pandas DataFrames straight into Send slices, we shim
    the metadata serializer's default hook so DataFrames don't blow it up.
    """
    try:
        import pandas as pd
    except ImportError:
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, pd.DataFrame):
        return {"__dataframe__": obj.to_dict("records"), "__columns__": list(obj.columns)}
    if isinstance(obj, pd.Series):
        return obj.to_list()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class _PickleFallbackSerde(JsonPlusSerializer):
    """Wraps JsonPlusSerializer so non-JSON-able payloads (pandas DataFrames in
    `state['raw']`) pickle-fallback even when msgpack triggers the UTF-8 path."""

    def __init__(self) -> None:
        super().__init__(pickle_fallback=True)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        try:
            return super().dumps_typed(obj)
        except (TypeError, ValueError):
            return "pickle", pickle.dumps(obj)


class _MetadataSerde(JsonPlusSerializer):
    """Used for checkpoint metadata (JSON-only path inside SqliteSaver). Adds a
    DataFrame fallback so node `writes` containing DataFrames don't crash."""

    def _default(self, obj: Any) -> Any:
        try:
            return super()._default(obj)
        except TypeError:
            return _df_to_jsonable(obj)


def _slice_for_subagent(state: MarketState, name: str) -> dict:
    return {
        "target_date":  state["target_date"],
        "pattern_hits": [h for h in state.get("pattern_hits", [])
                          if h["target_subagent"] == name],
        "raw":          state.get("raw", {}),
        "leader_stack": state.get("leader_stack", []),
        "themes":       state.get("themes", {}),
        "main_theme":   state.get("main_theme"),
    }


def _dispatch(state: MarketState):
    active = {h["target_subagent"] for h in state.get("pattern_hits", [])}
    active &= set(SUBAGENT_NAMES)
    if not active:
        return ["join"]
    return [Send(name, _slice_for_subagent(state, name)) for name in active]


# Only these keys from a subagent's terminal state propagate back to the parent.
# Everything else (target_date, raw, themes, leader_stack, ...) is dropped to
# avoid LastValue conflicts when N subagents fan back in via reducers.
_SUBAGENT_OUTPUT_KEYS = {"candidates", "errors"}


def _wrap_subagent(compiled):
    """Wrap a compiled subgraph as a parent-graph node. Strips intra-subgraph
    state from the return so only reducer-annotated keys reach the parent."""

    def _node(state):
        out = compiled.invoke(state)
        return {k: v for k, v in out.items() if k in _SUBAGENT_OUTPUT_KEYS}

    return _node


def build_graph(checkpoint_path: str = "checkpoints.db"):
    g = StateGraph(MarketState)

    # STAGE A - SENSE
    g.add_node("market_sensor", market_sensor_node)
    g.add_node("index_cycle",   index_cycle_node)
    g.add_node("emotion",       emotion_node)
    g.add_node("cycle_switch",  cycle_switch_node)
    g.add_edge(START, "market_sensor")
    g.add_edge("market_sensor", "index_cycle")
    g.add_edge("index_cycle",   "emotion")
    g.add_edge("emotion",       "cycle_switch")

    # STAGE B - ANALYZE
    g.add_node("theme_analyst",   theme_analyst_node)
    g.add_node("leader_tracker",  leader_tracker_node)
    g.add_node("pattern_matcher", pattern_matcher_node)
    g.add_edge("cycle_switch",    "theme_analyst")
    g.add_edge("theme_analyst",   "leader_tracker")
    g.add_edge("leader_tracker",  "pattern_matcher")

    # STAGE C - DECIDE - sub-graphs as callable nodes (wrapped so only
    # reducer-annotated keys leak back to the parent state).
    g.add_node("weak_to_strong",   _wrap_subagent(build_w2s_subgraph()))
    g.add_node("first_board",      _wrap_subagent(build_fb_subgraph()))
    g.add_node("continuous",       _wrap_subagent(build_con_subgraph()))
    g.add_node("setback_reversal", _wrap_subagent(build_sr_subgraph()))
    g.add_node("join", lambda s: {})       # noop, lets reducer fold candidates
    g.add_conditional_edges("pattern_matcher", _dispatch,
                             [*SUBAGENT_NAMES, "join"])
    for name in SUBAGENT_NAMES:
        g.add_edge(name, "join")

    g.add_node("arbitrage",     arbitrage_node)
    g.add_node("risk_guard",    risk_guard_node)
    g.add_node("trade_planner", trade_planner_node)
    g.add_node("post_mortem",   post_mortem_node)
    g.add_edge("join",          "arbitrage")
    g.add_edge("arbitrage",     "risk_guard")
    g.add_edge("risk_guard",    "trade_planner")
    g.add_edge("trade_planner", "post_mortem")
    g.add_edge("post_mortem",   END)

    conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
    # Pickle-fallback serde so DataFrames in state["raw"] survive checkpointing.
    saver = SqliteSaver(conn, serde=_PickleFallbackSerde())
    # Override the metadata serializer (SqliteSaver uses a separate one) too.
    saver.jsonplus_serde = _MetadataSerde()
    return g.compile(checkpointer=saver)
