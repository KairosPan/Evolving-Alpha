# tests/test_web_market.py — 市场模块:JSON API + 盘面页(离线;tmp PITStore 经 YOUZI_SNAPSHOT 注入)
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from youzi_web.app import create_app

D1, D2 = date(2024, 6, 26), date(2024, 6, 27)


@pytest.fixture
def snap(tmp_path, monkeypatch):
    """两交易日的迷你 PIT 快照:走真 PITStore/SnapshotSource 全链路。"""
    from youzi.data.cache import PITStore
    store = PITStore(tmp_path)
    for d, zt in [
        (D1, pd.DataFrame({"code": ["600001"], "name": ["龙一"], "boards": [4],
                           "pct": [10.0], "industry": ["芯片"]})),
        (D2, pd.DataFrame({"code": ["600001", "600002", "600003"],
                           "name": ["龙一", "龙二", "首板"], "boards": [5, 2, 1],
                           "pct": [10.0, 10.0, 9.9], "industry": ["芯片", "芯片", "军工"],
                           "seal_amount": [2e8, 1e8, 5e7]})),
    ]:
        store.put("zt", d, zt)
        store.put("prev", d, pd.DataFrame())
        store.put("blowup", d, pd.DataFrame({"code": ["600004"], "name": ["炸了"], "pct": [3.0]}))
        store.put("dt", d, pd.DataFrame())
    store.put_ohlcv("600001", pd.DataFrame({
        "date": [D1, D2], "open": [10.0, 11.0], "high": [11.0, 12.1],
        "low": [9.9, 10.9], "close": [11.0, 12.1], "volume": [1e6, 1.5e6]}))
    store.put_calendar([D1, D2])
    monkeypatch.setenv("YOUZI_SNAPSHOT", str(tmp_path))
    return tmp_path


# ── JSON API ──────────────────────────────────────────────────────────────

def test_api_days(snap):
    r = TestClient(create_app()).get("/api/market/days")
    assert r.status_code == 200
    assert r.json()["days"] == ["2024-06-26", "2024-06-27"]


def test_api_brief_default_latest_day(snap):
    r = TestClient(create_app()).get("/api/market/brief")
    assert r.status_code == 200
    b = r.json()
    assert b["day"] == "2024-06-27"
    assert (b["limit_up_count"], b["blowup_count"], b["limit_down_count"]) == (3, 1, 0)
    assert b["max_board_height"] == 5
    assert b["echelon"][0]["boards"] == 5


def test_api_candidates_filter(snap):
    c = TestClient(create_app())
    all_ = c.get("/api/market/candidates", params={"day": "2024-06-27"}).json()
    assert [x["code"] for x in all_["candidates"]] == ["600001", "600002", "600003"]
    hi = c.get("/api/market/candidates",
               params={"day": "2024-06-27", "min_boards": 2}).json()
    assert [x["code"] for x in hi["candidates"]] == ["600001", "600002"]


def test_api_bars_window_and_honest_empty(snap):
    c = TestClient(create_app())
    r = c.get("/api/market/bars",
              params={"symbol": "cn:600001", "start": "2024-06-26", "end": "2024-06-27"}).json()
    assert r["n"] == 2 and r["bars"][-1]["close"] == 12.1
    empty = c.get("/api/market/bars",
                  params={"symbol": "600999", "start": "2024-06-26", "end": "2024-06-27"}).json()
    assert empty["n"] == 0 and "诚实空" in empty["note"]


def test_api_missing_day_is_loud_404(snap):
    r = TestClient(create_app()).get("/api/market/brief", params={"day": "2024-07-01"})
    assert r.status_code == 404
    assert "缺池" in r.json()["error"] or "快照" in r.json()["error"]


def test_api_bad_symbol_rejected(snap):
    r = TestClient(create_app()).get(
        "/api/market/bars",
        params={"symbol": "../../etc", "start": "2024-06-26", "end": "2024-06-27"})
    assert r.status_code == 400


# ── 盘面页 ────────────────────────────────────────────────────────────────

def test_board_page_renders(snap):
    r = TestClient(create_app()).get("/market/board")
    assert r.status_code == 200
    assert "涨停" in r.text and "龙一" in r.text
    assert "2024-06-27" in r.text            # 日期选择器含快照日
    assert "梯队" in r.text


def test_board_page_specific_day(snap):
    r = TestClient(create_app()).get("/market/board", params={"day": "2024-06-26"})
    assert r.status_code == 200
    assert "龙二" not in r.text              # D1 只有龙一


def test_board_page_no_snapshot_empty_state(monkeypatch):
    monkeypatch.delenv("YOUZI_SNAPSHOT", raising=False)
    r = TestClient(create_app()).get("/market/board")
    assert r.status_code == 200
    assert "未配置快照" in r.text            # 空态,不 500


def test_kline_fragment_svg(snap):
    r = TestClient(create_app()).get(
        "/market/kline", params={"symbol": "600001", "day": "2024-06-27"})
    assert r.status_code == 200
    assert "<svg" in r.text and "600001" in r.text
    assert "ratio-only-safe" in r.text or "前复权" in r.text   # 复权诚实标注


def test_market_in_shell_rail(snap):
    r = TestClient(create_app()).get("/research/harness")
    assert "/market/board" in r.text         # 📈 出现在外壳导航
