"""Allocate position across final_candidates within zone cap."""
from __future__ import annotations

from .risk_guard import _zone_total_max
from ..state import Candidate, MarketState, TradePlan


def trade_planner_node(state: MarketState) -> dict:
    finals = list(state.get("final_candidates", []))[:8]
    pos_max = _zone_total_max(
        state.get("emotion_phase", "warming"),
        state.get("index_phase", "oscillation"),
    )
    if not finals:
        plan: TradePlan = {
            "date": state["target_date"],
            "position_total_max": pos_max,
            "candidates": [],
            "avoid_list": [],
            "notes": "无候选,空仓",
        }
        return {"plan": plan}

    weights = [float(c.get("score", 0)) for c in finals]
    sw = sum(weights) or 1.0
    sized: list[Candidate] = []
    for c, w in zip(finals, weights):
        per = min(float(c.get("suggested_position", 0.10)), pos_max * (w / sw))
        sized.append({**c, "suggested_position": round(per, 4)})

    plan: TradePlan = {
        "date": state["target_date"],
        "position_total_max": pos_max,
        "candidates": sized,
        "avoid_list": [],
        "notes": f"{state.get('emotion_phase','?')} · {state.get('index_phase','?')}",
    }
    return {"plan": plan}
