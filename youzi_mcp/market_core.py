# youzi_mcp/market_core.py — youzi-market 桥的纯逻辑层(零 MCP 依赖,离线可测)。
# market 槽位:v1 只接 cn;其它市场值诚实报未接入(槽位在,机器不在——见 specs/2026-08-26)。
from __future__ import annotations

import re
from datetime import date as Date
from pathlib import Path

from youzi.data.source import GuardedSource
from youzi.replay.firewall import AsOfGuard
from youzi.universe.universe import build_universe

KNOWN_MARKETS = ("cn",)
_CN_CODE = re.compile(r"^\d{6}$")
_MAX_CANDIDATES = 80


def market_error(market: str) -> str | None:
    """market 槽位守卫:未接入的市场给明确指引,不臆造数据。"""
    if market not in KNOWN_MARKETS:
        return (f"市场 '{market}' 尚未接入(当前仅 cn;us/crypto 槽位已留,"
                "接入 checklist 见 docs/superpowers/specs/2026-08-26-youzi-market-framework.md)")
    return None


def parse_symbol(symbol: str) -> tuple[str, str]:
    """'cn:600519' → ('cn','600519');无前缀默认 cn(前缀是留给未来市场的槽位)。"""
    s = str(symbol).strip()
    market, sep, code = s.partition(":")
    if not sep:
        return "cn", s
    return market, code


def validate_cn_code(code: str) -> str | None:
    """模型可控输入,进任何取数路径前先验(6 位数字)。"""
    if not _CN_CODE.match(code):
        return f"非法 cn 代码 '{code}'(须 6 位数字)"
    return None


def available_days(snapshot_root: str) -> list[Date]:
    """快照里有 zt 池的交易日(YYYYMMDD.parquet 文件名),升序。"""
    days: list[Date] = []
    for p in sorted(Path(snapshot_root).glob("zt/*.parquet")):
        stem = p.stem
        try:
            days.append(Date(int(stem[:4]), int(stem[4:6]), int(stem[6:8])))
        except ValueError:
            continue
    return days


def market_brief(source, day: Date) -> dict:
    """当日盘面简报——全部取数经 GuardedSource(as_of=day),≤day 之外结构上够不到。"""
    gs = GuardedSource(source, AsOfGuard(day))
    uni = build_universe(gs, day)
    ups = uni.by_status("limit_up")
    blows = uni.by_status("blowup")
    downs = uni.by_status("limit_down")
    boards = [s.boards for s in ups if s.boards]
    tiers: dict[int, list[str]] = {}
    for s in ups:
        if s.boards and s.boards >= 2:
            tiers.setdefault(s.boards, []).append(s.name)
    n_up, n_blow = len(ups), len(blows)
    return {
        "market": "cn",
        "day": day.isoformat(),
        "limit_up_count": n_up,
        "blowup_count": n_blow,
        "limit_down_count": len(downs),
        "blowup_rate": round(n_blow / (n_up + n_blow), 3) if n_up + n_blow else None,
        "max_board_height": max(boards) if boards else None,
        "echelon": [{"boards": b, "count": len(ns), "names": ns[:5]}
                    for b, ns in sorted(tiers.items(), reverse=True)],
    }


def candidates(source, day: Date, min_boards: int = 1) -> dict:
    """当日涨停候选(按连板数降序)。boards 缺失诚实 None,min_boards>1 时不臆造为 0 保留。"""
    gs = GuardedSource(source, AsOfGuard(day))
    uni = build_universe(gs, day)
    ups = uni.by_status("limit_up")
    if min_boards > 1:
        ups = [s for s in ups if (s.boards or 0) >= min_boards]
    rows = sorted(ups, key=lambda s: -(s.boards or 0))
    return {
        "market": "cn",
        "day": day.isoformat(),
        "count": len(rows),
        "truncated": len(rows) > _MAX_CANDIDATES,
        "candidates": [{
            "code": s.code, "name": s.name, "boards": s.boards,
            "industry": s.industry, "pct": s.pct,
            "seal_amount": s.seal_amount, "first_seal_time": s.first_seal_time,
        } for s in rows[:_MAX_CANDIDATES]],
    }


def bars(source, code: str, start: Date, end: Date) -> dict:
    """日 K(经 GuardedSource,as_of=end)。空结果是诚实空(停牌/退市/未捕获),不伪造。"""
    gs = GuardedSource(source, AsOfGuard(end))
    df = gs.daily_ohlcv(code, start, end)
    rows = [{"date": str(r["date"]), "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r["volume"]}
            for _, r in df.iterrows()]
    out = {
        "market": "cn",
        "symbol": f"cn:{code}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "n": len(rows),
        "bars": rows,
        "adjust_note": "qfq 前复权、基准=采集时点;仅比值安全(ratio-only-safe),勿当绝对历史价",
    }
    if not rows:
        out["note"] = "无数据:停牌/退市/或快照未捕获该代码(诚实空,非零)"
    return out
