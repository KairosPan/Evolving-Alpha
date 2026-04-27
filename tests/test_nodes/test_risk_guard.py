from youzi_agent.nodes.risk_guard import risk_guard_node, _zone_total_max

def test_drop_w2s_in_decay_1():
    state = {
        "emotion_phase": "decay_1", "index_phase": "downtrend",
        "candidates": [
            {"code": "600202", "name": "x", "pattern_id": "L2_weak_to_strong",
             "score": 0.7, "reason": "r", "suggested_position": 0.1},
            {"code": "002438", "name": "y", "pattern_id": "L1_first_board",
             "score": 0.6, "reason": "r", "suggested_position": 0.1},
        ],
    }
    out = risk_guard_node(state)
    finals = out["final_candidates"]
    assert all(c["pattern_id"] != "L2_weak_to_strong" for c in finals)
    assert any("禁忌" in f for f in out["risk_flags"])

def test_drop_high_consec_in_chaos():
    state = {
        "emotion_phase": "chaos", "index_phase": "downtrend",
        "candidates": [
            {"code": "600202", "name": "x", "pattern_id": "first_to_continuous",
             "score": 0.7, "reason": "r", "suggested_position": 0.1, "consec_boards": 3},
        ],
    }
    out = risk_guard_node(state)
    assert out["final_candidates"] == []

def test_zone_total_max_warming():
    pos = _zone_total_max("warming", "uptrend")
    assert pos == 1.0

def test_zone_total_max_climax():
    pos = _zone_total_max("climax", "uptrend")
    assert pos <= 0.3
