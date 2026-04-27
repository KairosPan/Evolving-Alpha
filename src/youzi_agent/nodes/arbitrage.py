"""4 hardcoded arbitrage scanners."""
from __future__ import annotations

from ..state import Candidate, MarketState


def _ladder_arb(state: MarketState) -> list[Candidate]:
    # v1: pass-through; needs first-board filter inside same theme as 4-5B leader
    return []


def _complement_arb(state: MarketState) -> list[Candidate]:
    leaders = state.get("leader_stack", [])
    if not leaders:
        return []
    main = next((l for l in leaders if l["role"] == "total"), None)
    if not main or main["consec_boards"] < 5:
        return []
    same_theme_complements = [l for l in leaders
                              if l["role"] in {"complement", "companion"}
                              and l["consec_boards"] <= main["consec_boards"] - 3]
    return [{
        "code": l["code"], "name": l["name"], "pattern_id": "arb_complement",
        "score": 0.5,
        "reason": f"补涨套利·主龙{main['code']}({main['consec_boards']}B)同属性低位",
        "suggested_position": 0.05,
    } for l in same_theme_complements[:3]]


def _new_cycle_arb(state: MarketState) -> list[Candidate]:
    return []


def _drop_out_arb(state: MarketState) -> list[Candidate]:
    return []


def arbitrage_node(state: MarketState) -> dict:
    arbs: list[Candidate] = []
    arbs += _ladder_arb(state)
    arbs += _complement_arb(state)
    arbs += _new_cycle_arb(state)
    arbs += _drop_out_arb(state)
    return {"arb_opportunities": arbs}
