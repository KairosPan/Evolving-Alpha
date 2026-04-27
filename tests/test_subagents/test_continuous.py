import pandas as pd
from youzi_agent.subagents.continuous import build_con_subgraph

def test_continuous_picks_2b_in_main_theme():
    ztb_today = pd.DataFrame({
        "代码":         ["600202", "002438", "300999"],
        "名称":         ["中核科技", "江苏神通", "新票"],
        "连板数":       [3, 2, 2],
        "封单金额":     [3e8, 1e8, 0.4e8],
        "首次封板时间": ["09:35", "10:00", "13:50"],
        "炸板次数":     [0, 0, 1],
    })
    state = {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb_today},
        "themes": {"核电": {"name": "核电",
                            "members": ["600202", "002438", "300999"],
                            "leader": "600202", "phase": "vertical",
                            "catalysts": [], "resonance_score": 0.85}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "first_to_continuous",
                          "filter_desc": "x", "target_subagent": "continuous"}],
    }
    out = build_con_subgraph().invoke(state)
    codes = [c["code"] for c in out.get("candidates", [])]
    assert "600202" in codes or "002438" in codes
