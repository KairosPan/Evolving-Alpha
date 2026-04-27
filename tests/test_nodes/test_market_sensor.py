from unittest.mock import MagicMock
import pandas as pd
from youzi_agent.nodes.market_sensor import market_sensor_node

def test_market_sensor_populates_basic_stats():
    cli = MagicMock()
    ztb_today = pd.DataFrame({
        "代码": ["600000", "000001", "300750"],
        "名称": ["a", "b", "c"],
        "连板数": [1, 2, 4],
        "封单金额": [1.2e8, 0.5e8, 5e8],
        "首次封板时间": ["09:30", "10:15", "09:31"],
        "炸板次数": [0, 1, 0],
    })
    ztb_yest = pd.DataFrame({
        "代码": ["600000"], "名称": ["a"], "连板数": [1],
        "封单金额": [1e8], "首次封板时间": ["09:35"], "炸板次数": [2],
    })
    zb_yest = pd.DataFrame({"代码": ["000002", "300999"]})
    cli.limit_up_pool.side_effect = lambda d: ztb_today if d == "2026-04-25" else ztb_yest
    cli.blast_pool.return_value = zb_yest
    cli.index_daily.return_value = pd.DataFrame()
    cli.market_activity.return_value = pd.DataFrame([{"red_count": 2300}])

    out = market_sensor_node({"target_date": "2026-04-25"}, client=cli)
    assert out["limit_up_count"] == 3
    assert out["consec_top"] == 4
    assert "raw" in out
    assert "ztb_today" in out["raw"]
    # blast_rate = (limit_up_yesterday-still-limit_up-today) ratio approximation
    assert 0 <= out["blast_rate"] <= 1
