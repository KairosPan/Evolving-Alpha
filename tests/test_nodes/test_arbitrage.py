from youzi_agent.nodes.arbitrage import arbitrage_node

def test_complement_arb_emits_when_strong_leader_with_low_consec_companion():
    state = {
        "leader_stack": [
            {"code": "600202", "name": "中核科技", "consec_boards": 7,
             "role": "total", "sealed_amount": 2.0, "blast_today": False, "div_count": 0},
            {"code": "002438", "name": "江苏神通", "consec_boards": 2,
             "role": "complement", "sealed_amount": 0.5, "blast_today": False, "div_count": 0},
        ],
        "themes": {"核电": {"name": "核电", "members": ["600202", "002438"],
                            "leader": "600202", "phase": "vertical", "catalysts": [],
                            "resonance_score": 0.9}},
        "main_theme": "核电",
        "emotion_phase": "main_rise",
    }
    out = arbitrage_node(state)
    arbs = out["arb_opportunities"]
    assert any("补涨" in a["reason"] for a in arbs)

def test_arbitrage_returns_empty_when_no_leader():
    state = {"leader_stack": [], "themes": {}, "emotion_phase": "chaos"}
    out = arbitrage_node(state)
    assert out["arb_opportunities"] == []
