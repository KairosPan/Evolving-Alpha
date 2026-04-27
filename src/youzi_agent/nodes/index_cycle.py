"""Index-level phase + MACD."""
from __future__ import annotations

import pandas as pd

from ..state import MarketState


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    dif = _ema(closes, fast) - _ema(closes, slow)
    dea = _ema(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def _classify_phase(closes: pd.Series) -> str:
    if len(closes) < 60:
        return "oscillation"
    ma20 = closes.rolling(20).mean().iloc[-1]
    ma60 = closes.rolling(60).mean().iloc[-1]
    last = closes.iloc[-1]
    slope_60 = (closes.rolling(60).mean().iloc[-1] - closes.rolling(60).mean().iloc[-20]) / closes.iloc[-1]
    if last > ma60 and ma20 > ma60 and slope_60 > 0.005:
        return "uptrend"
    if last < ma60 and ma20 < ma60 and slope_60 < -0.005:
        return "downtrend"
    if abs(slope_60) < 0.002:
        return "oscillation"
    if slope_60 > 0:
        return "top" if last < ma20 * 0.97 else "uptrend"
    return "bottom" if last > ma20 * 1.03 else "downtrend"


def _summarize_macd(closes: pd.Series) -> dict:
    dif, dea, hist = _macd(closes)
    return {
        "dif": float(dif.iloc[-1]),
        "dea": float(dea.iloc[-1]),
        "hist": float(hist.iloc[-1]),
        "above_zero": bool(dif.iloc[-1] > 0),
        "golden_cross": bool(dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] >= dea.iloc[-1])
                         if len(dif) >= 2 else False,
    }


def index_cycle_node(state: MarketState) -> dict:
    raw = state.get("raw", {})
    sh = raw.get("idx_sh")
    cyb = raw.get("idx_cyb")
    if sh is None or len(sh) == 0:
        return {"errors": ["index_cycle: no idx_sh data"], "index_phase": "oscillation"}
    sh_closes = sh["close"].astype(float)
    cyb_closes = cyb["close"].astype(float) if cyb is not None and len(cyb) else sh_closes
    return {
        "index_phase":  _classify_phase(sh_closes),
        "sz_macd":      _summarize_macd(sh_closes),
        "cyb_macd":     _summarize_macd(cyb_closes),
        "market_volume": float(sh["amount"].iloc[-1]) if "amount" in sh.columns else 0.0,
        "big_cap_volume_ratio": 0.0,  # v1 placeholder, see spec §6.2
    }
