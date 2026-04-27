from youzi_agent.nodes.cycle_switch import cycle_switch_node

def test_cycle_switch_no_prev_state_degrades_safely():
    out = cycle_switch_node({"emotion_phase": "warming",
                              "limit_up_count": 60,
                              "consec_top": 5,
                              "target_date": "2026-04-25"},
                             prev_snapshot=None)
    assert out["is_new_cycle_day"] is False
    assert out["is_only_rebound"] is False
    assert any("无前日" in e for e in out.get("errors", []))

def test_cycle_switch_new_cycle_day():
    out = cycle_switch_node(
        {"emotion_phase": "recovery", "limit_up_count": 70, "consec_top": 5,
         "target_date": "2026-04-25"},
        prev_snapshot={"emotion_phase": "chaos", "consec_top": 2})
    assert out["is_new_cycle_day"] is True

def test_cycle_switch_money_effect_levels():
    for lu, expected in [(60, "positive"), (30, "neutral"), (10, "negative")]:
        out = cycle_switch_node(
            {"emotion_phase": "warming", "limit_up_count": lu, "consec_top": 3,
             "target_date": "2026-04-25"},
            prev_snapshot={"emotion_phase": "warming", "consec_top": 3})
        assert out["money_effect"] == expected
