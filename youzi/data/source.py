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


_OHLCV_RENAME = {"日期": "date", "开盘": "open", "收盘": "close",
                 "最高": "high", "最低": "low", "成交量": "volume"}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 日线中文列 -> 英文;date->date 对象;OHLCV->数值。空 -> 带列空 df。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    out = df.rename(columns=_OHLCV_RENAME).copy()
    out = out.loc[:, ~out.columns.duplicated()]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _ymd(day: Date) -> str:
    return day.strftime("%Y%m%d")


def _market_prefix(code: str) -> str:
    """code → 交易所前缀(sina/tencent 用 sh/sz/bj 前缀符号)。北交所先于沪判定(920 vs 9)。"""
    if code.startswith(("4", "8", "92")):
        return "bj"                                   # 北交所 43/83/87/88/920
    if code.startswith(("5", "6", "9")):
        return "sh"                                   # 沪主板 60 / 科创 68 / 沪 B 90 / 基金 5
    return "sz"                                        # 深主板 00 / 创业 30 / 深 B 20


def _fallback_ohlcv(providers, code: str, start: Date, end: Date) -> pd.DataFrame:
    """按序尝试多个 OHLCV 数据源,首个返回非空(规整后)即用 → 抗单端点故障(eastmoney 限流切 sina/tencent)。

    providers: list[callable(code, start, end) -> 规整后 DataFrame]。单源异常 → 记录并下一个;
    单源合法返回空(无数据)→ 也尝试下一个;**全部成功调用但都空** → 返回带列空帧(诚实"无数据");
    **全部抛异常**(没有任何成功调用,即全端点故障)→ re-raise 最后异常(不静默吞掉总故障)。
    """
    last_exc: Exception | None = None
    any_success = False
    for provider in providers:
        try:
            df = provider(code, start, end)
            any_success = True
        except Exception as e:                        # noqa: BLE001 — 单源故障 → 切下一源
            last_exc = e
            continue
        if df is not None and not df.empty:
            return df
    if not any_success and last_exc is not None:      # 全端点故障(非"无数据")→ loud,不静默
        raise last_exc
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])


def _retry_ak(fn, tries: int = 4, backoff: float = 1.0, sleep=None):
    """akshare 取数重试:网络抖动(connection reset 等)指数退避重试;ValueError(如炸板池 30 日限制)
    等确定性错误不重试。多日多窗实盘 eval 必需——否则单次瞬时抖动崩整轮。sleep 可注入便于测试。"""
    import time as _t
    slp = sleep if sleep is not None else _t.sleep
    last: Exception | None = None
    for k in range(tries):
        try:
            return fn()
        except ValueError:
            raise                       # akshare 确定性错误(范围限制/无数据),不重试
        except Exception as e:          # noqa: BLE001 — 网络抖动:退避重试
            last = e
            if k < tries - 1:
                slp(backoff * (2 ** k))
            else:
                raise
    raise last  # pragma: no cover


class MarketDataSource(Protocol):
    """市场数据源契约(规整后英文列:code/name/boards/pct)。"""
    def trading_calendar(self) -> list[Date]: ...
    def zt_pool(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_previous(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_blowup(self, day: Date) -> pd.DataFrame: ...
    def dt_pool(self, day: Date) -> pd.DataFrame: ...
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame: ...


class AkshareSource:
    """真实 akshare 适配器。函数名见 PROJECT_STATE.md 第 4 节。"""

    def __init__(self) -> None:
        import akshare as ak
        self._ak = ak
        # ② OHLCV 多源 fallback 链:eastmoney(主)→ sina → tencent,抗单端点限流/故障
        self._ohlcv_providers = [self._ohlcv_eastmoney, self._ohlcv_sina, self._ohlcv_tencent]

    def trading_calendar(self) -> list[Date]:
        df = _retry_ak(lambda: self._ak.tool_trade_date_hist_sina())
        return [pd.to_datetime(d).date() for d in df["trade_date"]]

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_em(date=_ymd(day))))

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_previous_em(date=_ymd(day))))

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_zbgc_em(date=_ymd(day))))

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_dtgc_em(date=_ymd(day))))

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        # ② 多源 fallback:任一源限流/故障自动切换,全部 qfq 复权、规整为统一英文列
        return _fallback_ohlcv(self._ohlcv_providers, code, start, end)

    def _ohlcv_eastmoney(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        return _normalize_ohlcv(_retry_ak(lambda: self._ak.stock_zh_a_hist(
            symbol=code, period="daily", start_date=_ymd(start),
            end_date=_ymd(end), adjust="qfq")))

    def _ohlcv_sina(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        sym = _market_prefix(code) + code
        return _normalize_ohlcv(_retry_ak(lambda: self._ak.stock_zh_a_daily(
            symbol=sym, start_date=_ymd(start), end_date=_ymd(end), adjust="qfq")))

    def _ohlcv_tencent(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        sym = _market_prefix(code) + code
        return _normalize_ohlcv(_retry_ak(lambda: self._ak.stock_zh_a_hist_tx(
            symbol=sym, start_date=_ymd(start), end_date=_ymd(end), adjust="qfq")))


class GuardedSource:
    """把每次取数日期过 AsOfGuard,杜绝未来函数。包裹任意 MarketDataSource。"""

    def __init__(self, inner: MarketDataSource, guard: AsOfGuard) -> None:
        self._inner = inner
        self._guard = guard

    def trading_calendar(self) -> list[Date]:
        # 有意不 guard:交易日历是公开的"哪些日子开市"日期表,非未来价格/结果;回放与
        # 收益尺需用它枚举(含未来)交易日定位 entry/exit,守界只对**取数日**(下方各池/OHLCV)生效。
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

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)            # 打分时刻 as_of≥t+N 合法;越界(end>as_of)→ LookaheadError
        return self._inner.daily_ohlcv(code, start, end)
