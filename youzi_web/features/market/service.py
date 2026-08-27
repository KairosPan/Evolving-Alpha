# youzi_web/features/market/service.py
from __future__ import annotations

import os
from datetime import date as Date
from pathlib import Path

from youzi.data.cache import PITStore
from youzi.data.snapshot_source import SnapshotSource
# market_core 是 web / dsh(youzi_mcp)两壳共用的读模型(纯逻辑、零 MCP 依赖)
from youzi_mcp import market_core as core


def snapshot_root() -> str | None:
    return os.environ.get("YOUZI_SNAPSHOT") or None


def _source() -> SnapshotSource:
    return SnapshotSource(PITStore(Path(snapshot_root())))


def days() -> list[str]:
    root = snapshot_root()
    return [d.isoformat() for d in core.available_days(root)] if root else []


def pick_day(day: str | None) -> Date | None:
    """day 参数(可空)→ 交易日;空取快照最新;无快照 → None。"""
    if day:
        return Date.fromisoformat(day)
    avail = days()
    return Date.fromisoformat(avail[-1]) if avail else None


def brief(day: Date) -> dict:
    return core.market_brief(_source(), day)


def candidates(day: Date, min_boards: int = 1) -> dict:
    return core.candidates(_source(), day, min_boards=min_boards)


def bars(code: str, start: Date, end: Date) -> dict:
    return core.bars(_source(), code, start, end)


def kline_geometry(rows: list[dict], width: int = 620, height: int = 240,
                   pad: int = 12) -> dict | None:
    """日 K → SVG 几何(纯函数)。红涨绿跌由模板按 up 着色;n=0 → None。"""
    if not rows:
        return None
    lo = min(r["low"] for r in rows)
    hi = max(r["high"] for r in rows)
    span = (hi - lo) or 1.0
    n = len(rows)
    slot = (width - 2 * pad) / n
    body_w = max(3.0, slot * 0.6)

    def y(v: float) -> float:
        return pad + (hi - v) / span * (height - 2 * pad)

    candles = []
    for i, r in enumerate(rows):
        x_mid = pad + slot * i + slot / 2
        top, bot = max(r["open"], r["close"]), min(r["open"], r["close"])
        candles.append({
            "x": round(x_mid - body_w / 2, 1), "w": round(body_w, 1),
            "body_y": round(y(top), 1),
            "body_h": round(max(1.0, y(bot) - y(top)), 1),
            "wick_x": round(x_mid, 1),
            "wick_y1": round(y(r["high"]), 1), "wick_y2": round(y(r["low"]), 1),
            "up": r["close"] >= r["open"],
            "date": r["date"],
        })
    return {"width": width, "height": height, "candles": candles,
            "hi": hi, "lo": lo,
            "first_date": rows[0]["date"], "last_date": rows[-1]["date"]}


def board_context(day: str | None, min_boards: int = 1) -> dict:
    """盘面页上下文。无快照 → no_snapshot 空态;缺池日由调用方捕获 SnapshotMissingError。"""
    if not snapshot_root():
        return {"no_snapshot": True, "days": [], "day": None,
                "min_boards": min_boards, "brief": None, "cands": []}
    d = pick_day(day)
    if d is None:
        return {"no_snapshot": True, "days": [], "day": None,
                "min_boards": min_boards, "brief": None, "cands": []}
    return {"no_snapshot": False, "days": days(), "day": d.isoformat(),
            "min_boards": min_boards, "brief": brief(d),
            "cands": candidates(d, min_boards=min_boards)["candidates"]}
