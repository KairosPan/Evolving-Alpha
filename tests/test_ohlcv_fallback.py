# tests/test_ohlcv_fallback.py
"""② OHLCV 多源 fallback:eastmoney→sina→tencent 抗单端点故障(纯离线编排测试)。"""
from datetime import date

import pandas as pd
import pytest

from youzi.data.source import _fallback_ohlcv, _market_prefix

D1, D2 = date(2026, 6, 1), date(2026, 6, 2)
_COLS = ["date", "open", "high", "low", "close", "volume"]


def _df(rows=None):
    return pd.DataFrame(rows or [], columns=_COLS)


class _Provider:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, 0

    def __call__(self, code, start, end):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.result


def test_first_nonempty_wins_others_not_called():
    p1, p2 = _Provider(_df([(D1, 1, 1, 1, 1, 1)])), _Provider(_df([(D2, 2, 2, 2, 2, 2)]))
    out = _fallback_ohlcv([p1, p2], "600000", D1, D2)
    assert len(out) == 1 and p1.calls == 1 and p2.calls == 0


def test_falls_through_on_exception():
    p1, p2 = _Provider(exc=ConnectionError("eastmoney 限流")), _Provider(_df([(D2, 2, 2, 2, 2, 2)]))
    out = _fallback_ohlcv([p1, p2], "600000", D1, D2)
    assert len(out) == 1 and p1.calls == 1 and p2.calls == 1


def test_falls_through_on_empty():
    p1, p2 = _Provider(_df()), _Provider(_df([(D2, 2, 2, 2, 2, 2)]))
    out = _fallback_ohlcv([p1, p2], "600000", D1, D2)
    assert len(out) == 1 and p2.calls == 1


def test_all_empty_returns_empty_frame():
    p1, p2 = _Provider(_df()), _Provider(_df())
    out = _fallback_ohlcv([p1, p2], "600000", D1, D2)
    assert out.empty and list(out.columns) == _COLS


def test_all_raise_reraises_last():
    p1, p2 = _Provider(exc=ConnectionError("a")), _Provider(exc=TimeoutError("b"))
    with pytest.raises(TimeoutError):
        _fallback_ohlcv([p1, p2], "600000", D1, D2)


def test_exception_then_empty_returns_empty_not_raise():
    # 一源故障、另一源合法返回"无数据" → 返回空(不 raise,因有成功调用)
    p1, p2 = _Provider(exc=ConnectionError("a")), _Provider(_df())
    out = _fallback_ohlcv([p1, p2], "600000", D1, D2)
    assert out.empty


def test_market_prefix():
    assert _market_prefix("600000") == "sh"     # 沪主板
    assert _market_prefix("688981") == "sh"     # 科创
    assert _market_prefix("900957") == "sh"     # 沪 B
    assert _market_prefix("000001") == "sz"     # 深主板
    assert _market_prefix("300750") == "sz"     # 创业板
    assert _market_prefix("830799") == "bj"     # 北交所 8
    assert _market_prefix("920099") == "bj"     # 北交所 92(先于 9→sh 判定)
    assert _market_prefix("430047") == "bj"     # 北交所 4
