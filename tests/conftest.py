# tests/conftest.py
"""共享 fixtures:FakeSource 返回内存样例帧,测试离线。"""
from __future__ import annotations

from datetime import date
import pandas as pd
import pytest


class FakeSource:
    """实现 MarketDataSource 协议的内存假源,用于离线测试。"""

    def __init__(self, frames: dict[tuple[str, date], pd.DataFrame],
                 calendar: list[date]):
        self._frames = frames
        self._calendar = calendar

    def trading_calendar(self) -> list[date]:
        return list(self._calendar)

    def _get(self, kind: str, day: date) -> pd.DataFrame:
        return self._frames.get((kind, day), pd.DataFrame())

    def zt_pool(self, day: date) -> pd.DataFrame:
        return self._get("zt", day)

    def zt_pool_previous(self, day: date) -> pd.DataFrame:
        return self._get("prev", day)

    def zt_pool_blowup(self, day: date) -> pd.DataFrame:
        return self._get("blowup", day)

    def dt_pool(self, day: date) -> pd.DataFrame:
        return self._get("dt", day)


@pytest.fixture
def sample_calendar() -> list[date]:
    return [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
