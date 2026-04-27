from unittest.mock import MagicMock
from youzi_agent.nodes.pattern_matcher import pattern_matcher_node, _lookup_route, ROUTE_TABLE

def test_lookup_exact_match():
    out = _lookup_route("recovery", True, "first_div", "uptrend")
    assert "L1_first_board" in out

def test_lookup_wildcard_succession():
    # climax with any succession → []
    assert _lookup_route("climax", False, "healthy", "uptrend") == []

def test_pattern_matcher_emits_hits():
    state = {
        "emotion_phase": "recovery", "is_new_cycle_day": True,
        "succession_status": "first_div", "index_phase": "uptrend",
        "limit_up_count": 60, "consec_top": 4, "blast_rate": 0.18,
        "use_llm": False,
    }
    out = pattern_matcher_node(state)
    ids = [h["pattern_id"] for h in out["pattern_hits"]]
    assert "L1_first_board" in ids
    targets = {h["target_subagent"] for h in out["pattern_hits"]}
    assert "first_board" in targets

def test_pattern_matcher_edge_triggers_llm(monkeypatch):
    state = {
        "emotion_phase": "warming", "is_new_cycle_day": False,
        "succession_status": "healthy", "index_phase": "uptrend",
        "limit_up_count": 1010,             # edge: ±10% of 1000 threshold
        "consec_top": 4, "blast_rate": 0.18,
        "use_llm": True,
    }
    fake_edge = MagicMock(emotion_phase="chaos", confidence=0.85, reason="近冰点")
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = fake_edge
    monkeypatch.setattr("youzi_agent.nodes.pattern_matcher.get_llm", lambda *a, **k: fake_llm)
    out = pattern_matcher_node(state)
    assert out["emotion_phase"] == "chaos"

def test_pattern_matcher_climax_emits_no_hits():
    state = {
        "emotion_phase": "climax", "is_new_cycle_day": False,
        "succession_status": "healthy", "index_phase": "uptrend",
        "limit_up_count": 150, "consec_top": 8, "blast_rate": 0.20,
        "use_llm": False,
    }
    out = pattern_matcher_node(state)
    assert out["pattern_hits"] == []


def test_setback_reversal_route_disabled_in_v1():
    """v1: divergence + first_div should NOT activate setback_reversal subagent."""
    state = {
        "emotion_phase": "divergence", "is_new_cycle_day": False,
        "succession_status": "first_div", "index_phase": "uptrend",
        "limit_up_count": 50, "consec_top": 3, "blast_rate": 0.20,
        "use_llm": False,
    }
    out = pattern_matcher_node(state)
    targets = {h["target_subagent"] for h in out["pattern_hits"]}
    assert "setback_reversal" not in targets
