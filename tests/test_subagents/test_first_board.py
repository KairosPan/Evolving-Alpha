import pandas as pd
from youzi_agent.subagents.first_board import build_fb_subgraph, fb_filter, fb_score

def _state():
    ztb_yest = pd.DataFrame({
        "代码":         ["600202", "002438", "300999", "600000", "688001"],
        "名称":         ["中核科技", "江苏神通", "新票", "浦发ST", "次新票"],
        "连板数":       [1, 1, 1, 1, 1],
        "封单金额":     [2e8, 1.2e8, 0.5e8, 0.8e8, 1e8],
        "首次封板时间": ["09:35", "09:50", "10:15", "10:00", "09:31"],
        "炸板次数":     [0, 0, 1, 0, 0],
        "上市天数":     [800, 600, 1000, 700, 30],
        "开盘价":       [10.0, 8.0, 5.0, 6.0, 20.0],
        "涨停价":       [11.0, 8.8, 5.5, 6.6, 22.0],
    })
    # Inject ST in name, next-new with 上市天数<60
    ztb_yest.loc[3, "名称"] = "ST 浦发"
    return {
        "target_date": "2026-04-25",
        "raw": {"ztb_yesterday": ztb_yest},
        "themes": {"核电": {"name": "核电", "members": ["600202", "002438"],
                            "leader": "600202", "phase": "vertical", "catalysts": [],
                            "resonance_score": 0.8}},
        "main_theme": "核电",
        "pattern_hits": [{"pattern_id": "L1_first_board", "filter_desc": "x",
                          "target_subagent": "first_board"}],
    }

def test_fb_filter_excludes_st_and_new():
    state = _state()
    out = fb_filter(state)
    pool = out["_fb_pool"]
    codes = {r["代码"] for r in pool}
    assert "688001" not in codes  # 次新
    assert "600000" not in codes  # ST

def test_fb_score_main_theme_bonus():
    state = _state()
    state.update(fb_filter(state))
    out = fb_score(state)
    scored = {r["代码"]: r["_score"] for r in out["_fb_scored"]}
    assert scored["600202"] > scored.get("300999", 0)

def test_first_board_subgraph_e2e():
    g = build_fb_subgraph()
    out = g.invoke(_state())
    assert "candidates" in out
    assert any(c["pattern_id"] == "L1_first_board" for c in out["candidates"])
    assert all(0 <= c["score"] <= 1 for c in out["candidates"])
