from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from youzi_agent.data.akshare_client import AkshareClient, _retry, _coerce_percent_strings

def test_retry_succeeds_on_third_attempt():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("flaky")
        return "ok"
    assert _retry(flaky, attempts=3, backoff=1.0) == "ok"
    assert calls["n"] == 3

def test_retry_raises_after_max_attempts():
    def always_fail():
        raise RuntimeError("nope")
    with pytest.raises(RuntimeError):
        _retry(always_fail, attempts=2, backoff=1.0)

def test_limit_up_pool_caches(tmp_path):
    cli = AkshareClient(cache_dir=tmp_path)
    df_fixture = pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "连板数": [1]})
    with patch("youzi_agent.data.akshare_client.ak") as ak_mock:
        ak_mock.stock_zt_pool_em.return_value = df_fixture
        out1 = cli.limit_up_pool("2026-04-25")
        out2 = cli.limit_up_pool("2026-04-25")
        assert ak_mock.stock_zt_pool_em.call_count == 1
        assert out1.equals(out2)

def test_market_activity_fallback_when_legu_fails(tmp_path):
    cli = AkshareClient(cache_dir=tmp_path)
    spot = pd.DataFrame({"涨跌幅": [1.5, -0.3, 9.95, -2.0, 5.0]})
    with patch("youzi_agent.data.akshare_client.ak") as ak_mock:
        ak_mock.stock_market_activity_legu.side_effect = RuntimeError("missing")
        ak_mock.stock_zh_a_spot_em.return_value = spot
        out = cli.market_activity("2026-04-25")
        assert int(out.iloc[0]["red_count"]) == 3
        assert int(out.iloc[0]["limit_up"]) == 1

def test_market_activity_strips_percent_strings(tmp_path):
    cli = AkshareClient(cache_dir=tmp_path)
    legu_with_pct = pd.DataFrame({"item": ["上涨家数", "活跃度"], "value": ["3001", "48.02%"]})
    with patch("youzi_agent.data.akshare_client.ak") as ak_mock:
        ak_mock.stock_market_activity_legu.return_value = legu_with_pct
        out = cli.market_activity("2026-04-25")
        # After cleaning, value column should be float
        assert out["value"].dtype.kind == "f"
        assert float(out.loc[out["item"] == "活跃度", "value"].iloc[0]) == 48.02
