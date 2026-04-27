"""Persist per-day report.json + report.md + state_snapshot.json."""
from __future__ import annotations

import json
from pathlib import Path

from ..reporting import render_markdown, state_to_json
from ..state import MarketState

_SNAPSHOT_FIELDS = ("emotion_phase", "consec_top", "limit_up_count",
                    "main_theme", "succession_status", "is_new_cycle_day",
                    "is_only_rebound", "five_day_pos")


def post_mortem_node(state: MarketState, *, runs_dir: str | Path = "runs") -> dict:
    date = state["target_date"]
    out_dir = Path(runs_dir) / date
    out_dir.mkdir(parents=True, exist_ok=True)

    serialized = state_to_json(state)
    (out_dir / "report.json").write_text(json.dumps(serialized, ensure_ascii=False, indent=2))
    (out_dir / "report.md").write_text(render_markdown(state))

    snapshot = {k: state.get(k) for k in _SNAPSHOT_FIELDS if k in state}
    (out_dir / "state_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))

    return {"review": {"written_to": str(out_dir),
                        "candidates_count": len(state.get("plan", {}).get("candidates", [])),
                        "errors_count": len(state.get("errors", []))}}
