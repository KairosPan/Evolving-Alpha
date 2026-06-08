from __future__ import annotations

from datetime import date as Date
from pathlib import Path

import pandas as pd


class PITStore:
    """point-in-time 缓存:每日每类原始帧落一个 parquet,路径 = root/kind/YYYYMMDD.parquet。

    一旦写入即视为"该日 as-of 快照",不应被未来修订覆盖(由调用方保证幂等)。
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, kind: str, day: Date) -> Path:
        return self._root / kind / f"{day.strftime('%Y%m%d')}.parquet"

    def has(self, kind: str, day: Date) -> bool:
        return self._path(kind, day).exists()

    def get(self, kind: str, day: Date) -> pd.DataFrame | None:
        p = self._path(kind, day)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def put(self, kind: str, day: Date, df: pd.DataFrame) -> None:
        p = self._path(kind, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)

    def _ohlcv_path(self, code: str) -> Path:
        return self._root / "ohlcv" / f"{code}.parquet"

    def has_ohlcv(self, code: str) -> bool:
        return self._ohlcv_path(code).exists()

    def get_ohlcv(self, code: str) -> pd.DataFrame | None:
        p = self._ohlcv_path(code)
        return pd.read_parquet(p) if p.exists() else None

    def put_ohlcv(self, code: str, df: pd.DataFrame) -> None:
        p = self._ohlcv_path(code)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)

    def put_calendar(self, days: list[Date]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": [d.isoformat() for d in days]}).to_parquet(
            self._root / "calendar.parquet", index=False)

    def get_calendar(self) -> list[Date] | None:
        p = self._root / "calendar.parquet"
        if not p.exists():
            return None
        return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]
