from youzi_agent.nodes.trade_planner import trade_planner_node

def test_plan_caps_total_position():
    state = {
        "target_date": "2026-04-25",
        "emotion_phase": "warming", "index_phase": "uptrend",
        "final_candidates": [
            {"code": "600202", "name": "x", "pattern_id": "L1_first_board",
             "score": 0.9, "reason": "r", "suggested_position": 0.5},
            {"code": "002438", "name": "y", "pattern_id": "L1_first_board",
             "score": 0.7, "reason": "r", "suggested_position": 0.5},
            {"code": "300999", "name": "z", "pattern_id": "L1_first_board",
             "score": 0.6, "reason": "r", "suggested_position": 0.5},
        ],
    }
    out = trade_planner_node(state)
    plan = out["plan"]
    assert plan["date"] == "2026-04-25"
    total = sum(c["suggested_position"] for c in plan["candidates"])
    assert total <= plan["position_total_max"] + 1e-9

def test_plan_empty_when_no_candidates():
    out = trade_planner_node({
        "target_date": "2026-04-25", "emotion_phase": "chaos",
        "index_phase": "downtrend", "final_candidates": [],
    })
    assert out["plan"]["candidates"] == []
