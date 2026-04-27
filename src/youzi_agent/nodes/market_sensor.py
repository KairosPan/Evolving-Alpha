"""Stage A entry: pull all the day's data into state['raw']."""
from __future__ import annotations

import pandas as pd

from ..data.akshare_client import AkshareClient
from ..state import MarketState


def _prev_trading_day(date: str) -> str:
    # Naive: last calendar weekday. Holidays handled by data layer (cache returns empty).
    d = pd.Timestamp(date) - pd.Timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _calc_blast_rate(ztb_today: pd.DataFrame, zb_yest: pd.DataFrame) -> float:
    """Approximation: yesterday-blasted / (yesterday-blasted + today-still-up)."""
    blasted = len(zb_yest) if zb_yest is not None else 0
    sustained = len(ztb_today)
    denom = blasted + sustained
    return round(blasted / denom, 4) if denom else 0.0


def market_sensor_node(state: MarketState, *, client: AkshareClient | None = None) -> dict:
    cli = client or AkshareClient()
    date = state["target_date"]
    prev = _prev_trading_day(date)
    try:
        raw = {
            "ztb_today":     cli.limit_up_pool(date),
            "ztb_yesterday": cli.limit_up_pool(prev),
            "zb_yesterday":  cli.blast_pool(prev),
            "idx_sh":        cli.index_daily("sh000001"),
            "idx_cyb":       cli.index_daily("sz399006"),
            "activity":      cli.market_activity(date),
        }
    except Exception as e:
        return {"errors": [f"market_sensor: data fetch failed: {e}"]}

    ztb = raw["ztb_today"]
    consec_col = "连板数" if "连板数" in ztb.columns else "连板"
    return {
        "raw": raw,
        "limit_up_count": int(len(ztb)),
        "consec_top": int(ztb[consec_col].max()) if len(ztb) else 0,
        "blast_rate": _calc_blast_rate(ztb, raw["zb_yesterday"]),
    }
