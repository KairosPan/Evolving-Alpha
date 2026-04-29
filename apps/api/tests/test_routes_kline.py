import pandas as pd
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import build_app


def _fake_kline(*args, **kwargs):
    return pd.DataFrame({
        "date": ["2026-04-25", "2026-04-26"],
        "open": [10.0, 10.5],
        "high": [10.6, 11.0],
        "low": [9.8, 10.4],
        "close": [10.5, 10.9],
        "volume": [1_000_000, 1_200_000],
    })


@patch("youzi_agent.data.akshare_client.get_kline", side_effect=_fake_kline)
def test_kline_returns_ohlc(_mock, tmp_path):
    client = TestClient(build_app(
        checkpoint_path=str(tmp_path / "ckpt.db"),
        runs_dir=str(tmp_path / "runs"),
        cache_dir=str(tmp_path / "cache"),
    ))
    r = client.get("/api/kline/600519?days=2")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "600519"
    assert len(body["bars"]) == 2
    assert body["bars"][0] == {
        "time": "2026-04-25", "open": 10.0, "high": 10.6,
        "low": 9.8, "close": 10.5, "volume": 1_000_000,
    }
    assert "limit_up_days" in body
