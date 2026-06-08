# tests/test_snapshot_source.py
from datetime import date

import pandas as pd
import pytest

from youzi.data.cache import PITStore
from youzi.data.snapshot_source import SnapshotSource, SnapshotMissingError


def test_pools_roundtrip_and_missing_raises(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 2)])
    store.put("zt", date(2026, 6, 2), pd.DataFrame({"code": ["A"], "boards": [2]}))
    src = SnapshotSource(store)
    assert src.trading_calendar() == [date(2026, 6, 2)]
    assert list(src.zt_pool(date(2026, 6, 2))["code"]) == ["A"]
    with pytest.raises(SnapshotMissingError):
        src.dt_pool(date(2026, 6, 2))                  # 未存 → 报错(不完整快照大声抓住)


def test_missing_calendar_raises(tmp_path):
    with pytest.raises(SnapshotMissingError):
        SnapshotSource(PITStore(tmp_path)).trading_calendar()


def test_ohlcv_slice_date_objects_and_missing_empty(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                       (date(2026, 6, 3), 10.6, 12, 10, 12.0, 200),
                       (date(2026, 6, 4), 12.1, 13, 12, 12.5, 300)],
                      columns=["date", "open", "high", "low", "close", "volume"])
    store.put_ohlcv("A", df)
    src = SnapshotSource(store)
    got = src.daily_ohlcv("A", date(2026, 6, 2), date(2026, 6, 3))
    assert list(got["date"]) == [date(2026, 6, 2), date(2026, 6, 3)]   # 切片 + date 对象
    assert isinstance(got["date"].iloc[0], date)
    assert src.daily_ohlcv("MISSING", date(2026, 6, 2), date(2026, 6, 3)).empty   # 缺 code → 空
