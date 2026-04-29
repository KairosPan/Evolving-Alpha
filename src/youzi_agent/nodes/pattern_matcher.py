"""Truth-table routing + optional LLM tiebreaker for emotion_phase."""
from __future__ import annotations

import os

from langgraph.types import interrupt

from ..llm.deepseek import get_llm
from ..llm.schemas import PatternEdgeOut
from ..state import MarketState, PatternHit

# (emotion, is_new_cycle_day, succession_status, index_phase) -> [pattern_id]
# v2 note: S2_setback_reversal is deferred until kline_loader is implemented;
# any route that would activate it is mapped to [] until then.
ROUTE_TABLE: dict[tuple[str, object, str, str], list[str]] = {
    ("chaos",      False, "broken",     "*"): ["L1_first_board", "L2_weak_to_strong"],
    ("recovery",   True,  "first_div",  "uptrend"): ["L1_first_board", "L2_weak_to_strong"],
    ("recovery",   "*",   "*",          "*"): ["L1_first_board"],
    ("warming",    False, "healthy",    "uptrend"): ["L4_strong_2b", "first_to_continuous"],
    ("warming",    "*",   "*",          "*"): ["L1_first_board", "first_to_continuous"],
    ("main_rise",  False, "healthy",    "uptrend"): ["L4_strong_2b"],
    ("climax",     "*",   "*",          "*"): [],
    ("divergence", False, "first_div",  "*"): [],   # v2: re-enable when kline_loader exists
    ("divergence", False, "second_div", "*"): [],
    ("decay_1",    "*",   "*",          "*"): [],
    ("decay_2",    "*",   "*",          "*"): [],
    ("decay_mid",  "*",   "*",          "*"): [],
}

PATTERN_TO_SUBAGENT = {
    "L1_first_board":      "first_board",
    "L2_weak_to_strong":   "weak_to_strong",
    "L4_strong_2b":        "first_board",
    "first_to_continuous": "continuous",
    "S2_setback_reversal": "setback_reversal",
}

PATTERN_DESC = {
    "L1_first_board":      "主流板块辨识度首板",
    "L2_weak_to_strong":   "极致弱转强",
    "L4_strong_2b":        "强势 2 板",
    "first_to_continuous": "一进二接力",
    "S2_setback_reversal": "首阴反包",
}


def _lookup_route(emotion: str, is_new: bool, succession: str, index_phase: str) -> list[str]:
    keys_to_try = [
        (emotion, is_new, succession, index_phase),
        (emotion, "*",   succession, index_phase),
        (emotion, is_new, "*",       index_phase),
        (emotion, "*",   "*",        index_phase),
        (emotion, is_new, succession, "*"),
        (emotion, "*",   succession, "*"),
        (emotion, is_new, "*",       "*"),
        (emotion, "*",   "*",        "*"),
    ]
    for k in keys_to_try:
        if k in ROUTE_TABLE:
            return ROUTE_TABLE[k]
    return []


def _is_edge_case(state: MarketState) -> bool:
    lu = state.get("limit_up_count", 0)
    if 900 <= lu <= 1100 or 3900 <= lu <= 4100 or 90 <= lu <= 110:
        return True
    if state.get("blast_rate", 0) > 0.40:
        return True
    return False


EDGE_PROMPT = """规则给出的 emotion_phase 是 {rule_phase},但以下指标边缘:
- 涨停家数 {lu}, 炸板率 {br:.1%}, 最高连板 {top}
- 五日线位置 {five_pos}
请给出你认为更准的 emotion_phase 和 confidence,并简述判断依据(80 字内)。"""


def pattern_matcher_node(state: MarketState) -> dict:
    emotion = state.get("emotion_phase", "warming")
    succession = state.get("succession_status", "healthy")
    index_phase = state.get("index_phase", "oscillation")
    is_new = bool(state.get("is_new_cycle_day", False))

    state_patch: dict = {}
    if state.get("use_llm", True) and _is_edge_case(state):
        try:
            llm = get_llm(0.2).with_structured_output(PatternEdgeOut)
            edge = llm.invoke(EDGE_PROMPT.format(
                rule_phase=emotion,
                lu=state.get("limit_up_count", 0),
                br=state.get("blast_rate", 0.0),
                top=state.get("consec_top", 0),
                five_pos=state.get("five_day_pos", "?"),
            ))
            if edge.confidence > 0.7 and edge.emotion_phase != emotion:
                state_patch = {
                    "emotion_phase": edge.emotion_phase,
                    "errors": [f"pattern_matcher LLM 改判 → {edge.emotion_phase} ({edge.reason})"],
                }
                emotion = edge.emotion_phase
        except Exception as e:
            state_patch = {"errors": [f"pattern_matcher LLM failed: {e}"]}

    pattern_ids = _lookup_route(emotion, is_new, succession, index_phase)
    hits: list[PatternHit] = [
        {"pattern_id": pid,
         "filter_desc": PATTERN_DESC.get(pid, pid),
         "target_subagent": PATTERN_TO_SUBAGENT[pid]}
        for pid in pattern_ids if pid in PATTERN_TO_SUBAGENT
    ]
    result = {"pattern_hits": hits, **state_patch}
    if not os.environ.get("YOUZI_AUTO_RESUME"):
        review = interrupt({
            "node": "pattern_matcher",
            "snapshot": {
                "pattern_hits": hits,
                "emotion_phase": emotion,
                "succession_status": succession,
                "index_phase": index_phase,
            },
        })
        if isinstance(review, dict) and "pattern_hits" in review:
            result["pattern_hits"] = review["pattern_hits"]
    return result
