from unittest.mock import MagicMock
import pandas as pd
from youzi_agent.nodes.theme_analyst import theme_analyst_node, _rule_fallback

def _fake_state():
    ztb = pd.DataFrame({
        "代码": ["600202", "002438", "600988"],
        "名称": ["中核科技", "江苏神通", "赤峰黄金"],
        "连板数": [3, 2, 1],
        "所属行业": ["核能", "核能", "黄金"],
    })
    return {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb},
        "limit_up_count": 3,
        "consec_top": 3,
        "sentiment_value": 2200,
    }

def test_theme_analyst_no_llm_uses_industry_grouping():
    state = _fake_state()
    state["use_llm"] = False
    out = theme_analyst_node(state)
    assert "themes" in out
    assert "核能" in out["themes"] or "黄金" in out["themes"]
    assert out["theme_axis"] in {"horizontal", "vertical", "switching", "exhausted"}

def test_theme_analyst_llm_path(monkeypatch):
    state = _fake_state()
    state["use_llm"] = True
    fake_out = MagicMock()
    fake_out.themes = [MagicMock(model_dump=lambda: {
        "name": "核电", "members": ["600202", "002438"], "leader": "600202",
        "phase": "vertical", "catalysts": ["政策"], "resonance_score": 0.85
    })]
    fake_out.main_theme = "核电"
    fake_out.theme_axis = "vertical"
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = fake_out
    monkeypatch.setattr("youzi_agent.nodes.theme_analyst.get_llm", lambda *a, **k: fake_llm)
    out = theme_analyst_node(state)
    assert out["main_theme"] == "核电"
    assert out["themes"]["核电"]["resonance_score"] == 0.85

def test_theme_analyst_llm_failure_falls_back(monkeypatch):
    state = _fake_state()
    state["use_llm"] = True
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("api down")
    monkeypatch.setattr("youzi_agent.nodes.theme_analyst.get_llm", lambda *a, **k: fake_llm)
    out = theme_analyst_node(state)
    assert "errors" in out and any("theme_analyst" in e for e in out["errors"])
    assert "themes" in out  # fallback still produces themes
