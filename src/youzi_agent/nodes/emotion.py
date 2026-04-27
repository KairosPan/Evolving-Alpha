"""Map (red_count, MA5, blast_rate, …) to one of 9 emotion phases."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from ..state import EmotionPhase, MarketState

ICE_THRESHOLD = 1000
CLIMAX_THRESHOLD = 4000
FLAT_DELTA = 5  # |Δ MA5| < 5 → flat


def _ma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - n:i + 1]) / n)
    return out


def _ma5_turn(red_counts: list[float]) -> str:
    if len(red_counts) < 7:
        return "flat"
    ma5 = _ma(red_counts, 5)
    today, yest, prev = ma5[-1], ma5[-2], ma5[-3]
    if today is None or yest is None or prev is None:
        return "flat"
    d_today = today - yest
    d_yest = yest - prev
    if abs(d_today) < FLAT_DELTA:
        return "flat"
    if d_today > 0 and d_yest <= 0:
        return "turn_up"
    if d_today < 0 and d_yest >= 0:
        return "turn_down"
    if d_today > 0 and d_yest > 0:
        return "continue_up"
    if d_today < 0 and d_yest < 0:
        return "continue_down"
    return "flat"


def classify_emotion(*, red_count: int, ma5: float, ma3: float, ma5_turn: str,
                     blast_rate: float, consec_top: int, lu_count: int) -> EmotionPhase:
    if red_count <= ICE_THRESHOLD:
        return "chaos"
    if red_count >= CLIMAX_THRESHOLD and lu_count > 100:
        return "climax"
    if ma5_turn == "turn_up":
        return "recovery" if ma5 < 2000 else "warming"
    if ma5_turn == "continue_up" and consec_top >= 5:
        return "main_rise"
    if ma5_turn == "continue_up":
        return "warming"
    if ma5_turn == "turn_down":
        return "divergence" if blast_rate > 0.30 else "decay_1"
    if ma5_turn == "continue_down":
        return "decay_2"
    return "warming"


def emotion_node(state: MarketState) -> dict:
    activity = state.get("raw", {}).get("activity")
    if activity is None or len(activity) == 0:
        return {"errors": ["emotion: no activity history"], "emotion_phase": "warming",
                "sentiment_value": int(state.get("limit_up_count", 0) * 30)}
    red = list(activity["red_count"].astype(int)) if "red_count" in activity.columns else []
    if not red:
        return {"errors": ["emotion: red_count missing"], "emotion_phase": "warming",
                "sentiment_value": 2000}
    ma5_today = sum(red[-5:]) / 5 if len(red) >= 5 else sum(red) / len(red)
    ma3_today = sum(red[-3:]) / 3 if len(red) >= 3 else ma5_today
    turn = _ma5_turn(red)
    phase = classify_emotion(
        red_count=red[-1], ma5=ma5_today, ma3=ma3_today, ma5_turn=turn,
        blast_rate=state.get("blast_rate", 0.0),
        consec_top=state.get("consec_top", 0),
        lu_count=state.get("limit_up_count", 0),
    )
    five_pos: Literal["above", "top_horizontal", "below", "bottom_grinding"]
    if ma5_today > 2500:
        five_pos = "above" if turn in {"continue_up", "turn_up"} else "top_horizontal"
    else:
        five_pos = "below" if turn in {"continue_down", "turn_down"} else "bottom_grinding"
    return {
        "emotion_phase": phase,
        "sentiment_value": int(red[-1]),
        "five_day_pos": five_pos,
    }
