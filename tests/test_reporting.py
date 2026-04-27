from youzi_agent.reporting import render_markdown, state_to_json

def test_render_markdown_contains_key_sections():
    state = {
        "target_date": "2026-04-25",
        "emotion_phase": "warming",
        "limit_up_count": 60, "consec_top": 5, "blast_rate": 0.18,
        "five_day_pos": "above", "is_new_cycle_day": True,
        "main_theme": "核电",
        "themes": {"核电": {"name": "核电", "members": ["600202"],
                            "leader": "600202", "phase": "vertical",
                            "catalysts": [], "resonance_score": 0.85}},
        "leader_stack": [{"code": "600202", "name": "中核科技",
                          "consec_boards": 4, "role": "total",
                          "sealed_amount": 2.5, "blast_today": False, "div_count": 0}],
        "plan": {"date": "2026-04-25", "position_total_max": 1.0,
                 "candidates": [{"code": "600202", "name": "中核科技",
                                  "pattern_id": "L1_first_board", "score": 0.8,
                                  "reason": "封单 2.5 亿", "suggested_position": 0.1}],
                 "avoid_list": [], "notes": "warming · uptrend"},
        "risk_flags": [], "arb_opportunities": [], "errors": [],
    }
    md = render_markdown(state)
    assert "情绪诊断" in md
    assert "核电" in md
    assert "600202" in md

def test_state_to_json_drops_raw():
    s = {"target_date": "2026-04-25", "raw": {"big": "df"}, "emotion_phase": "warming"}
    out = state_to_json(s)
    assert "raw" not in out
    assert out["emotion_phase"] == "warming"
