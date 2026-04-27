"""Per-trading-day parquet cache decorator."""
from __future__ import annotations

import functools
import hashlib
import re
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

T = TypeVar("T", bound=pd.DataFrame)

_DATE_RE = re.compile(r"\d{4}-?\d{2}-?\d{2}")


def _extract_date(args: tuple, kwargs: dict) -> str:
    """Find the trading-date argument among positional/kw args."""
    if "date" in kwargs and isinstance(kwargs["date"], str):
        return _normalize(kwargs["date"])
    for a in args:
        if isinstance(a, str) and _DATE_RE.fullmatch(a.replace("-", "")):
            return _normalize(a)
    return "undated"


def _normalize(d: str) -> str:
    d = d.replace("-", "")
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def _arg_hash(args: tuple, kwargs: dict) -> str:
    payload = repr(args) + repr(sorted(kwargs.items()))
    return hashlib.md5(payload.encode()).hexdigest()[:8]


def disk_cache(cache_dir: str | Path = "data_cache", ttl: str = "eod") -> Callable:
    """Cache the wrapped function's pandas DataFrame return value to parquet.

    Layout: {cache_dir}/{date}/{fn_name}_{argshash}.parquet
    Pass `_refresh=True` to bypass the cache for a single call.
    `ttl="eod"` means "valid forever within the same trading date".
    """
    base = Path(cache_dir)

    def deco(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        @functools.wraps(fn)
        def wrapper(*args, _refresh: bool = False, **kwargs):
            date = _extract_date(args, kwargs)
            sig = _arg_hash(args, kwargs)
            day_dir = base / date
            fname = f"{fn.__name__}_{sig}.parquet" if (args or kwargs) else f"{fn.__name__}.parquet"
            # Single-arg backward-compat: if only one arg and it's the date, drop the hash suffix
            if len(args) <= 1 and not kwargs and date != "undated":
                fname = f"{fn.__name__}.parquet"
            path = day_dir / fname
            if path.exists() and not _refresh:
                return pd.read_parquet(path)
            df = fn(*args, **kwargs)
            day_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            return df
        return wrapper
    return deco
