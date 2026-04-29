"""Allocate position across final_candidates within zone cap."""
from __future__ import annotations

import os

from langgraph.types import interrupt

from .risk_guard import _zone_total_max
from ..state import Candidate, MarketState, TradePlan


def trade_planner_node(state: MarketState) -> dict:
    finals = list(state.get("final_candidates", []))[:8]
    pos_max = state.get("position_total_max_override")
    if pos_max is None:
        pos_max = _zone_total_max(
            state.get("emotion_phase", "warming"),
            state.get("index_phase", "oscillation"),
        )
    pos_max = float(pos_max)

    if not finals:
        plan: TradePlan = {
            "date": state["target_date"],
            "position_total_max": pos_max,
            "candidates": [],
            "avoid_list": [],
            "notes": "无候选,空仓",
        }
    else:
        weights = [float(c.get("score", 0)) for c in finals]
        sw = sum(weights) or 1.0
        sized: list[Candidate] = []
        for c, w in zip(finals, weights):
            per = min(float(c.get("suggested_position", 0.10)), pos_max * (w / sw))
            sized.append({**c, "suggested_position": round(per, 4)})

        plan = {
            "date": state["target_date"],
            "position_total_max": pos_max,
            "candidates": sized,
            "avoid_list": [],
            "notes": f"{state.get('emotion_phase','?')} · {state.get('index_phase','?')}",
        }

    # at end of function — both branches above set `plan`
    result: dict = {"plan": plan}
    if not os.environ.get("YOUZI_AUTO_RESUME"):
        review = interrupt({
            "node": "trade_planner",
            "snapshot": {
                "plan": plan,
                "final_candidates": list(state.get("final_candidates", [])),
            },
        })
        if isinstance(review, dict) and "plan" in review:
            result["plan"] = review["plan"]
    return result
