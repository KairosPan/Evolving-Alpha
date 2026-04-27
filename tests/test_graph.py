from unittest.mock import patch, MagicMock
import pandas as pd
from youzi_agent.graph import build_graph

def _ztb_today():
    return pd.DataFrame({
        "代码":         ["600202", "002438"],
        "名称":         ["中核科技", "江苏神通"],
        "连板数":       [3, 2],
        "封单金额":     [3e8, 1e8],
        "首次封板时间": ["09:30", "10:00"],
        "炸板次数":     [0, 0],
        "所属行业":     ["核能", "核能"],
        "上市天数":     [800, 600],
        "开盘价":       [10.0, 8.0],
        "涨停价":       [11.0, 8.8],
    })

def _ztb_yest():
    return pd.DataFrame({
        "代码":         ["600202", "002438"],
        "名称":         ["中核科技", "江苏神通"],
        "连板数":       [2, 1],
        "封单金额":     [2e8, 1e8],
        "首次封板时间": ["09:35", "09:50"],
        "炸板次数":     [0, 0],
        "上市天数":     [800, 600],
        "开盘价":       [9.5, 7.5],
        "涨停价":       [10.0, 8.0],
    })

def _activity():
    return pd.DataFrame([
        {"date": f"2026-04-{d:02d}", "red_count": rc}
        for d, rc in zip(range(15, 26),
                         [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100])
    ])

def test_full_graph_runs_end_to_end_no_llm(tmp_path):
    cli = MagicMock()
    cli.limit_up_pool.side_effect = lambda d: _ztb_today() if d == "2026-04-25" else _ztb_yest()
    cli.blast_pool.return_value = pd.DataFrame()
    cli.index_daily.return_value = pd.DataFrame({
        "close": [3000 + i for i in range(100)],
        "amount": [1e10] * 100,
    })
    cli.market_activity.return_value = _activity()
    with patch("youzi_agent.nodes.market_sensor.AkshareClient", return_value=cli):
        g = build_graph(checkpoint_path=str(tmp_path / "ck.db"))
        out = g.invoke(
            {"target_date": "2026-04-25", "use_llm": False},
            config={"configurable": {"thread_id": "test"}},
        )
    assert "plan" in out
    assert out["plan"]["date"] == "2026-04-25"
