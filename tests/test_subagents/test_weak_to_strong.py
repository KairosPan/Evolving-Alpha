import pandas as pd
from youzi_agent.subagents.weak_to_strong import build_w2s_subgraph

def test_w2s_picks_yesterday_blast_with_today_gap_up():
    ztb_yest = pd.DataFrame({
        "代码": ["600202"],          # yesterday: limited up but blast >=2
        "名称": ["中核科技"],
        "连板数": [1],
        "封单金额": [0.3e8],
        "首次封板时间": ["14:30"],
        "炸板次数": [3],
        "涨停价": [11.0],
        "收盘价": [11.0],
    })
    ztb_today = pd.DataFrame({
        "代码": ["600202"],
        "名称": ["中核科技"],
        "连板数": [2],
        "封单金额": [4e8],
        "首次封板时间": ["09:33"],     # 5min 内秒板
        "炸板次数": [0],
        "开盘价": [11.6],              # 高开 5%+
        "昨日收盘": [11.0],
        "涨停价": [12.1],
    })
    state = {
        "target_date": "2026-04-25",
        "raw": {"ztb_today": ztb_today, "ztb_yesterday": ztb_yest},
        "themes": {"核电": {"name": "核电", "members": ["600202"], "leader": "600202",
                            "phase": "vertical", "catalysts": [], "resonance_score": 0.8}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "L2_weak_to_strong", "filter_desc": "x",
                          "target_subagent": "weak_to_strong"}],
    }
    out = build_w2s_subgraph().invoke(state)
    assert any(c["code"] == "600202" for c in out.get("candidates", []))
