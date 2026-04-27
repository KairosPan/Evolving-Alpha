"""Cross-day flags: new_cycle_day / only_rebound / money_effect."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..state import MarketState


def _load_prev_snapshot(date: str, runs_dir: Path) -> Optional[dict]:
    from datetime import datetime, timedelta
    d = datetime.strptime(date, "%Y-%m-%d")
    for back in range(1, 8):  # look up to 7 calendar days back
        p = runs_dir / (d - timedelta(days=back)).strftime("%Y-%m-%d") / "state_snapshot.json"
        if p.exists():
            return json.loads(p.read_text())
    return None


def cycle_switch_node(state: MarketState,
                      *, runs_dir: str | Path = "runs",
                      prev_snapshot: Optional[dict] | object = ...) -> dict:
    if prev_snapshot is ...:
        prev_snapshot = _load_prev_snapshot(state["target_date"], Path(runs_dir))

    today_phase = state.get("emotion_phase")
    today_top = state.get("consec_top", 0)
    lu = state.get("limit_up_count", 0)

    money_effect = "positive" if lu > 50 else "neutral" if lu > 20 else "negative"

    if not prev_snapshot:
        return {
            "is_new_cycle_day": False,
            "is_only_rebound": False,
            "money_effect": money_effect,
            "errors": ["cycle_switch: 无前日 snapshot,标志位降级为 False"],
        }

    prev_phase = prev_snapshot.get("emotion_phase")
    prev_top = prev_snapshot.get("consec_top", 0)

    is_new = (
        prev_phase in {"chaos", "decay_2"}
        and today_phase in {"recovery", "warming"}
        and today_top >= prev_top
    )
    is_only_rebound = (
        prev_phase in {"decay_2", "decay_1"}
        and today_phase in {"recovery", "warming"}
        and today_top < 4
    )

    return {
        "is_new_cycle_day": bool(is_new),
        "is_only_rebound": bool(is_only_rebound),
        "money_effect": money_effect,
    }
