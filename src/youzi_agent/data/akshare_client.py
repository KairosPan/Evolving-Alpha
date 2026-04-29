"""Single IO boundary — every node reads data through this client."""
from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd

from .cache import disk_cache


def _retry(fn: Callable, attempts: int = 3, backoff: float = 1.5):
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(backoff ** i)
    assert last is not None
    raise last


def _ymd(date: str) -> str:
    return date.replace("-", "")


def _coerce_percent_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame with percent-string values converted to floats.

    For each object-dtype column:
    1. Any individual cell whose string representation matches
       ``^-?\\d+(\\.\\d+)?%$`` is stripped of its ``%`` suffix and replaced
       with the equivalent float value.
    2. After percent stripping, ``pd.to_numeric`` is applied with
       ``errors='ignore'``: if every value in the column can be converted to a
       number the column is cast to float64; otherwise the column is left
       as-is (mixed object).

    This handles both all-string columns (e.g. ``["3001", "48.02%"]``) and
    columns with mixed content (floats + one percent string + a date string).
    """
    import re
    _PCT_RE = re.compile(r"^-?\d+(\.\d+)?%$")

    def _maybe_strip_pct(v):
        if isinstance(v, str) and _PCT_RE.match(v):
            return float(v.rstrip("%"))
        return v

    out = df.copy()
    for col in out.columns:
        if out[col].dtype.kind != "O":
            continue
        out[col] = out[col].map(_maybe_strip_pct)
        try:
            out[col] = pd.to_numeric(out[col])
        except (ValueError, TypeError):
            # Column has non-numeric values (e.g. date strings mixed with
            # floats).  Cast everything to str so pyarrow can serialize the
            # column uniformly.
            out[col] = out[col].astype(str)
    return out


class AkshareClient:
    def __init__(self, cache_dir: str | Path = "data_cache"):
        self.cache_dir = Path(cache_dir)
        # Decorate methods at instance level so cache_dir is honored.
        for name in [
            "limit_up_pool", "blast_pool", "index_daily", "stock_kline",
            "market_activity", "concept_members_ths", "concept_list_ths",
            "code_list",
        ]:
            wrapped = disk_cache(cache_dir=self.cache_dir, ttl="eod")(getattr(self, name))
            setattr(self, name, wrapped)

    def limit_up_pool(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_zt_pool_em(date=_ymd(date)))

    def blast_pool(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_zt_pool_zbgc_em(date=_ymd(date)))

    def index_daily(self, symbol: str) -> pd.DataFrame:
        # symbol uses akshare convention e.g. "sh000001"
        return _retry(lambda: ak.stock_zh_index_daily_em(symbol=symbol))

    def stock_kline(self, code: str, end_date: str, lookback_days: int = 60) -> pd.DataFrame:
        start = (pd.Timestamp(end_date) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
        return _retry(lambda: ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start, end_date=_ymd(end_date),
            adjust="qfq",
        ))

    def market_activity(self, date: str) -> pd.DataFrame:
        try:
            df = _retry(lambda: ak.stock_market_activity_legu())
            df = _coerce_percent_strings(df)
            if "date" not in df.columns:
                df = df.assign(date=date)
            return df
        except Exception:
            spot = _retry(lambda: ak.stock_zh_a_spot_em())
            return pd.DataFrame([{
                "date":        date,
                "red_count":   int((spot["涨跌幅"] > 0).sum()),
                "green_count": int((spot["涨跌幅"] < 0).sum()),
                "limit_up":    int((spot["涨跌幅"] >= 9.9).sum()),
            }])

    def concept_members_ths(self, theme_name: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_board_concept_cons_ths(symbol=theme_name))

    def concept_list_ths(self, date: str) -> pd.DataFrame:
        # date arg is only for cache partitioning; the akshare call itself ignores it
        return _retry(lambda: ak.stock_board_concept_name_ths())

    def code_list(self, date: str) -> pd.DataFrame:
        return _retry(lambda: ak.stock_info_a_code_name())


_default_client: AkshareClient | None = None


def _client() -> AkshareClient:
    global _default_client
    if _default_client is None:
        _default_client = AkshareClient()
    return _default_client


def get_kline(code: str, days: int = 60) -> pd.DataFrame:
    """Module-level convenience wrapper around AkshareClient.stock_kline.

    Returns a DataFrame with columns date/open/high/low/close/volume.
    Uses today as end_date and lookback_days = max(days * 2, 60) to absorb
    akshare's end-window slop. The caller can ``.tail(days)`` to trim.
    """
    end_date = _dt.date.today().isoformat()
    df = _client().stock_kline(code, end_date=end_date, lookback_days=max(days * 2, 60))
    rename = {"日期": "date", "开盘": "open", "收盘": "close",
              "最高": "high", "最低": "low", "成交量": "volume"}
    df = df.rename(columns=rename)
    keep = ["date", "open", "high", "low", "close", "volume"]
    return df[[c for c in keep if c in df.columns]].copy()
