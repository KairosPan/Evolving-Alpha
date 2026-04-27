import pandas as pd
from youzi_agent.subagents.setback_reversal import build_sr_subgraph

def _kline(closes, opens=None):
    opens = opens or [c * 0.99 for c in closes]
    return pd.DataFrame({
        "日期": pd.date_range("2026-04-15", periods=len(closes)),
        "开盘": opens, "收盘": closes,
        "最高": [c * 1.02 for c in closes],
        "最低": [c * 0.98 for c in closes],
        "成交量": [1e7] * len(closes),
        "涨跌幅": [0.0] + [(closes[i]/closes[i-1]-1)*100 for i in range(1, len(closes))],
    })

def test_sr_picks_yin_eat_yang_after_recent_limit_up():
    # 600202: 5 days ago limit-up (10%), today is yin engulfing yesterday open
    closes = [10.0, 11.0, 11.5, 11.7, 11.0, 10.5, 10.2, 9.8]
    opens  = [10.0, 10.0, 11.2, 11.5, 11.4, 10.8, 10.6, 10.5]
    klines = {"600202": _kline(closes, opens)}
    state = {
        "target_date": "2026-04-22",
        "raw": {"klines_by_code": klines},
        "themes": {"核电": {"name": "核电", "members": ["600202"], "leader": "600202",
                            "phase": "switching", "catalysts": [], "resonance_score": 0.6}},
        "main_theme": "核电",
        "emotion_phase": "divergence",
        "pattern_hits": [{"pattern_id": "S2_setback_reversal", "filter_desc": "x",
                          "target_subagent": "setback_reversal"}],
    }
    out = build_sr_subgraph().invoke(state)
    assert any(c["code"] == "600202" for c in out.get("candidates", []))
