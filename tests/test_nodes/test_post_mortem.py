import json
from pathlib import Path
from youzi_agent.nodes.post_mortem import post_mortem_node

def test_post_mortem_writes_files(tmp_path):
    state = {
        "target_date": "2026-04-25", "emotion_phase": "warming",
        "limit_up_count": 60, "consec_top": 5, "blast_rate": 0.1,
        "main_theme": "核电", "themes": {}, "leader_stack": [],
        "plan": {"date": "2026-04-25", "position_total_max": 1.0,
                 "candidates": [], "avoid_list": [], "notes": ""},
        "risk_flags": [], "arb_opportunities": [], "errors": [],
        "raw": {"a": "b"},
    }
    out = post_mortem_node(state, runs_dir=tmp_path)
    day_dir = Path(tmp_path) / "2026-04-25"
    assert (day_dir / "report.md").exists()
    assert (day_dir / "report.json").exists()
    assert (day_dir / "state_snapshot.json").exists()
    snap = json.loads((day_dir / "state_snapshot.json").read_text())
    assert snap["emotion_phase"] == "warming"
    assert "review" in out
