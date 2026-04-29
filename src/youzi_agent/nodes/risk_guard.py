"""10-rule risk filter; outputs final_candidates (replace semantics)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from langgraph.types import interrupt

from ..state import Candidate, MarketState


@dataclass
class Taboo:
    name: str
    desc: str
    predicate: Callable[[MarketState, Candidate], bool]
    drop: bool = True


TABOOS: list[Taboo] = [
    Taboo("no_chase_climax", "高潮日不接力首封",
          lambda s, c: s.get("emotion_phase") == "climax"),
    Taboo("no_w2s_in_decay", "退潮初期不做弱转强",
          lambda s, c: s.get("emotion_phase") == "decay_1"
                         and c.get("pattern_id") == "L2_weak_to_strong"),
    Taboo("max_consec_in_chaos", "情绪冰点最高连板 ≥ 3 不接力",
          lambda s, c: s.get("emotion_phase") == "chaos"
                         and int(c.get("consec_boards", 0)) >= 3),
    Taboo("avoid_st", "ST 股不进任何池",
          lambda s, c: "ST" in c.get("name", "") or "退" in c.get("name", "")),
    Taboo("no_w2s_in_main_rise", "主升期不接 weak_to_strong",
          lambda s, c: s.get("emotion_phase") == "main_rise"
                         and c.get("pattern_id") == "L2_weak_to_strong"),
    Taboo("no_setback_in_chaos", "冰点不做反包",
          lambda s, c: s.get("emotion_phase") == "chaos"
                         and c.get("pattern_id") == "S2_setback_reversal"),
    Taboo("no_first_board_in_climax", "高潮日不打首板",
          lambda s, c: s.get("emotion_phase") == "climax"
                         and c.get("pattern_id") == "L1_first_board"),
    Taboo("no_continuous_in_decay", "退潮不接连板",
          lambda s, c: s.get("emotion_phase") in {"decay_1", "decay_2"}
                         and c.get("pattern_id") == "first_to_continuous"),
    Taboo("low_score_threshold", "score < 0.4 不进 plan",
          lambda s, c: float(c.get("score", 0)) < 0.4),
    Taboo("no_action_when_index_top", "指数顶背离不出手",
          lambda s, c: s.get("index_phase") == "top"
                         and c.get("pattern_id") in {"L1_first_board", "L2_weak_to_strong"}),
]


_ZONE_BY_EMOTION = {
    "chaos":     0.20, "recovery":   0.50, "warming":   1.00,
    "main_rise": 1.00, "climax":     0.30, "divergence": 0.30,
    "decay_1":   0.30, "decay_mid":  0.20, "decay_2":   0.20,
}


def _zone_total_max(emotion_phase: str, index_phase: str) -> float:
    base = _ZONE_BY_EMOTION.get(emotion_phase, 0.20)
    if index_phase == "top":
        base = min(base, 0.30)
    if index_phase == "downtrend":
        base = min(base, 0.30)
    return base


def risk_guard_node(state: MarketState) -> dict:
    survivors: list[Candidate] = []
    flags: list[str] = []
    seen: set[str] = set()
    for c in state.get("candidates", []):
        if c["code"] in seen:
            continue
        seen.add(c["code"])
        kept = True
        for t in TABOOS:
            if t.predicate(state, c):
                flags.append(f"{c['code']} 触发禁忌「{t.desc}」")
                if t.drop:
                    kept = False
                    break
        if kept:
            survivors.append(c)
    survivors.sort(key=lambda c: -float(c.get("score", 0)))
    result: dict = {
        "final_candidates": survivors,
        "risk_flags": flags,
    }
    if not os.environ.get("YOUZI_AUTO_RESUME"):
        advisory_cap = _zone_total_max(
            state.get("emotion_phase", "warming"),
            state.get("index_phase", "oscillation"),
        )
        review = interrupt({
            "node": "risk_guard",
            "snapshot": {
                "risk_flags": flags,
                "candidates": [{"code": c["code"], "name": c.get("name", "")} for c in survivors],
                "plan_position_cap": advisory_cap,
            },
        })
        if isinstance(review, dict):
            if "risk_flags" in review:
                result["risk_flags"] = review["risk_flags"]
            if "position_total_max" in review:
                # propagate user override to state for trade_planner to consume
                result["position_total_max_override"] = float(review["position_total_max"])
    return result
