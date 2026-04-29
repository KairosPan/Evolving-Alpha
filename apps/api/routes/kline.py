"""GET /api/kline/{code} — OHLC + limit-up day markers."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from youzi_agent.data import akshare_client

router = APIRouter(prefix="/api")


@router.get("/kline/{code}")
def get_kline(code: str, request: Request,
              period: str = Query("daily"),
              days: int = Query(60, gt=0, le=400)) -> dict:
    if period != "daily":
        raise HTTPException(400, "v1 supports period=daily only")

    cache_dir = Path(request.app.state.cache_dir) / "kline"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{code}_daily.parquet"

    df: pd.DataFrame | None = None
    if cache_path.exists():
        try:
            df = pd.read_parquet(cache_path)
        except Exception:
            df = None

    if df is None or len(df) < days:
        df = akshare_client.get_kline(code, days=max(days, 60))
        try:
            df.to_parquet(cache_path)
        except Exception:
            pass

    df = df.tail(days).reset_index(drop=True)

    # Mark limit-up days: close >= prev_close * 1.099 (approx 10% cap).
    limit_up_days: list[str] = []
    closes = df["close"].astype(float).tolist()
    dates = df["date"].astype(str).tolist()
    for i in range(1, len(closes)):
        if closes[i] >= closes[i - 1] * 1.099:
            limit_up_days.append(dates[i])

    bars = [{
        "time": str(r["date"]),
        "open": float(r["open"]),
        "high": float(r["high"]),
        "low": float(r["low"]),
        "close": float(r["close"]),
        "volume": int(r["volume"]),
    } for _, r in df.iterrows()]

    return {"code": code, "period": period, "bars": bars, "limit_up_days": limit_up_days}
