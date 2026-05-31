from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from youzi.replay.firewall import AsOfGuard

# akshare 中文列 -> 统一英文列
_RENAME = {
    "代码": "code", "名称": "name", "连板数": "boards",
    "涨跌幅": "pct", "炸板次数": "blowups", "昨日连板数": "boards",
    "封板资金": "seal_amount",
    "换手率": "turnover_rate",
    "首次封板时间": "first_seal_time",
    "所属行业": "industry",
    "流通市值": "float_mcap",
}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "name", "boards", "pct", "blowups"])
    out = df.rename(columns=_RENAME).copy()
    out = out.loc[:, ~out.columns.duplicated()]  # 防 _RENAME 把多列映射到同名(如 boards)导致重复列
    if "code" in out.columns:
        out["code"] = out["code"].astype(str).str.zfill(6)
    for col in ("boards", "pct", "blowups", "seal_amount", "turnover_rate", "float_mcap"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _ymd(day: Date) -> str:
    return day.strftime("%Y%m%d")


class MarketDataSource(Protocol):
    """市场数据源契约(规整后英文列:code/name/boards/pct)。"""
    def trading_calendar(self) -> list[Date]: ...
    def zt_pool(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_previous(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_blowup(self, day: Date) -> pd.DataFrame: ...
    def dt_pool(self, day: Date) -> pd.DataFrame: ...


class AkshareSource:
    """真实 akshare 适配器。函数名见 PROJECT_STATE.md 第 4 节。"""

    def __init__(self) -> None:
        import akshare as ak
        self._ak = ak

    def trading_calendar(self) -> list[Date]:
        df = self._ak.tool_trade_date_hist_sina()
        return [pd.to_datetime(d).date() for d in df["trade_date"]]

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(self._ak.stock_zt_pool_em(date=_ymd(day)))

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return _normalize(self._ak.stock_zt_pool_previous_em(date=_ymd(day)))

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return _normalize(self._ak.stock_zt_pool_zbgc_em(date=_ymd(day)))

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(self._ak.stock_zt_pool_dtgc_em(date=_ymd(day)))


class GuardedSource:
    """把每次取数日期过 AsOfGuard,杜绝未来函数。包裹任意 MarketDataSource。"""

    def __init__(self, inner: MarketDataSource, guard: AsOfGuard) -> None:
        self._inner = inner
        self._guard = guard

    def trading_calendar(self) -> list[Date]:
        return self._inner.trading_calendar()

    def zt_pool(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool(day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool_previous(day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool_blowup(day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.dt_pool(day)
