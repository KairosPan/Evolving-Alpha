# tests/test_mcp_market.py — youzi_mcp.market_core 纯逻辑离线测试(不 import MCP、不触网)。
from datetime import date

import pandas as pd

from tests.conftest import FakeSource
from youzi_mcp import market_core as core

D = date(2024, 6, 27)


def _source() -> FakeSource:
    frames = {
        ("zt", D): pd.DataFrame({
            "code": ["600001", "600002", "600003"], "name": ["龙一", "龙二", "首板"],
            "boards": [5, 3, 1], "pct": [10.0, 10.0, 10.0],
            "industry": ["芯片", "芯片", "军工"], "seal_amount": [2e8, 1e8, 5e7],
        }),
        ("blowup", D): pd.DataFrame({"code": ["600004"], "name": ["炸了"], "pct": [3.0]}),
        ("dt", D): pd.DataFrame({"code": ["600005"], "name": ["跌停"], "pct": [-10.0]}),
    }
    ohlcv = {"600001": pd.DataFrame({
        "date": [date(2024, 6, 25), date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)],
        "open": [10.0, 10.5, 11.0, 12.1], "high": [10.5, 11.0, 12.1, 13.3],
        "low": [9.9, 10.4, 10.9, 12.0], "close": [10.5, 11.0, 12.1, 13.3],
        "volume": [1e6, 1.2e6, 1.5e6, 1.1e6],
    })}
    return FakeSource(frames, [D], ohlcv=ohlcv)


# ── market 槽位 ────────────────────────────────────────────────────────────

def test_market_slot_cn_ok_others_honest():
    assert core.market_error("cn") is None
    for m in ("us", "crypto", "xx"):
        err = core.market_error(m)
        assert err is not None and "尚未接入" in err


def test_parse_symbol_prefix_slot():
    assert core.parse_symbol("cn:600519") == ("cn", "600519")
    assert core.parse_symbol("600519") == ("cn", "600519")       # 无前缀默认 cn
    assert core.parse_symbol("crypto:BTC-USDT") == ("crypto", "BTC-USDT")  # 槽位可解析


def test_validate_cn_code_rejects_injection():
    assert core.validate_cn_code("600519") is None
    for bad in ("abc123", "60051", "6005199", "../../etc", "600519;rm"):
        assert core.validate_cn_code(bad) is not None


# ── 简报 / 候选 ────────────────────────────────────────────────────────────

def test_market_brief_counts_and_echelon():
    b = core.market_brief(_source(), D)
    assert (b["limit_up_count"], b["blowup_count"], b["limit_down_count"]) == (3, 1, 1)
    assert b["blowup_rate"] == 0.25                       # 1/(3+1)
    assert b["max_board_height"] == 5
    assert [t["boards"] for t in b["echelon"]] == [5, 3]  # ≥2 板、降序;首板不进梯队
    assert b["echelon"][0]["names"] == ["龙一"]


def test_candidates_sorted_and_filtered():
    c = core.candidates(_source(), D)
    assert [x["code"] for x in c["candidates"]] == ["600001", "600002", "600003"]
    c3 = core.candidates(_source(), D, min_boards=3)
    assert [x["code"] for x in c3["candidates"]] == ["600001", "600002"]
    assert c3["count"] == 2 and c3["truncated"] is False


# ── K 线与防火墙 ───────────────────────────────────────────────────────────

def test_bars_window_and_honest_empty():
    r = core.bars(_source(), "600001", date(2024, 6, 25), date(2024, 6, 27))
    assert r["n"] == 3                                    # 6/28 在 end 之后,不可见
    assert r["bars"][-1]["close"] == 12.1
    assert "ratio-only-safe" in r["adjust_note"]
    empty = core.bars(_source(), "600999", date(2024, 6, 25), date(2024, 6, 27))
    assert empty["n"] == 0 and "诚实空" in empty["note"]


def test_bars_guarded_by_as_of():
    # as_of=end:窗口截到 end,end 之后的行结构上够不到(经 GuardedSource)
    r = core.bars(_source(), "600001", date(2024, 6, 25), date(2024, 6, 26))
    assert [row["date"] for row in r["bars"]] == ["2024-06-25", "2024-06-26"]
