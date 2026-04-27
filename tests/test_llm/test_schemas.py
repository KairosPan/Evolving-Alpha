import pytest
from youzi_agent.llm.schemas import ThemeAnalystOut, PatternEdgeOut, ThemeOut

def test_theme_analyst_out_parses():
    payload = {
        "themes": [
            {"name": "核电", "members": ["600202", "002438"], "leader": "600202",
             "phase": "vertical", "catalysts": ["政策"], "resonance_score": 0.8}
        ],
        "main_theme": "核电",
        "theme_axis": "vertical",
    }
    out = ThemeAnalystOut.model_validate(payload)
    assert out.main_theme == "核电"
    assert out.themes[0].resonance_score == 0.8

def test_resonance_score_bounded():
    with pytest.raises(Exception):
        ThemeOut.model_validate({"name": "x", "members": [], "leader": None,
                                 "phase": "horizontal", "catalysts": [],
                                 "resonance_score": 1.5})

def test_pattern_edge_out():
    edge = PatternEdgeOut.model_validate({
        "emotion_phase": "warming", "confidence": 0.85, "reason": "MA5 拐头"
    })
    assert edge.confidence == 0.85
