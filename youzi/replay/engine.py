from __future__ import annotations

from datetime import date as Date, datetime as DateTime, time as Time

from youzi.data.calendar import trading_days_between
from youzi.features.builder import build_market_state
from youzi.replay.firewall import AsOfGuard
from youzi.data.source import GuardedSource
from youzi.schemas.market import MarketState


class ReplayEngine:
    """reset-free 历史回放:游标逐交易日前进,observe() 受防火墙保护。"""

    def __init__(self, source, start: Date, end: Date) -> None:
        self._days = trading_days_between(source.trading_calendar(), start, end)
        if not self._days:
            raise ValueError("回放区间内没有交易日")
        self._i = 0
        self._guard = AsOfGuard(self._days[0])
        self.guarded_source = GuardedSource(source, self._guard)
        self.history: list[float] = []      # 已走过日的 sentiment_raw
        self._last_observed_i: int = -1     # 防 observe() + step() 双写 history

    @property
    def cursor(self) -> Date:
        return self._days[self._i]

    def observe(self) -> MarketState:
        day = self.cursor
        as_of = DateTime.combine(day, Time(15, 0))   # 收盘快照
        st = build_market_state(day, self.guarded_source, list(self.history),
                                as_of=as_of)
        # 只在当日首次 observe 时把 sentiment_raw 计入历史(幂等)
        if self._last_observed_i != self._i:
            self.history.append(st.sentiment_raw)
            self._last_observed_i = self._i
        return st

    def step(self) -> bool:
        """推进到下一交易日。到末日返回 False。迭代间不 reset(reset-free)。
        自动 observe 当日以确保 history 被累积,即使调用方未显式 observe。"""
        self.observe()   # 幂等:若已观察则不重复写 history
        if self._i + 1 >= len(self._days):
            return False
        self._i += 1
        self._guard.advance(self.cursor)
        return True

    def reset_to(self, day: Date) -> None:
        """显式跳转(回放 seam),非自动;仅允许跳到区间内交易日。"""
        if day not in self._days:
            raise ValueError(f"{day} 不在回放交易日内")
        self._i = self._days.index(day)
        self._guard = AsOfGuard(day)
        self.guarded_source = GuardedSource(
            self.guarded_source._inner, self._guard)  # 重新包裹同一内层源
        self._last_observed_i = -1   # 重置观察标记,允许在新游标位置重新 observe
