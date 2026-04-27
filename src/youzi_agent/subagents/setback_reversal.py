"""首阴反包 sub-graph."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import SetbackReversalState


def _had_recent_limit_up(kline, lookback: int = 10) -> bool:
    """Return True if any of the `lookback` trading days *before* today hit a limit-up."""
    if "涨跌幅" not in kline.columns:
        return False
    # Exclude today (last row) then take the `lookback` most-recent rows.
    recent = kline.iloc[:-1].tail(lookback)
    return bool((recent["涨跌幅"].astype(float) >= 9.5).any())


def _is_yin_engulf(kline) -> bool:
    if len(kline) < 2:
        return False
    today = kline.iloc[-1]; yest = kline.iloc[-2]
    return bool(float(today["收盘"]) <= float(yest["开盘"]) * 1.005
                and float(today["收盘"]) < float(today["开盘"]))


def sr_filter(s: SetbackReversalState) -> dict:
    klines = s.get("raw", {}).get("klines_by_code", {})
    pool = []
    for code, kline in klines.items():
        if _had_recent_limit_up(kline) and _is_yin_engulf(kline):
            pool.append({"code": code, "kline": kline})
    return {"_sr_pool": pool}


def sr_score(s) -> dict:
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    emotion = s.get("emotion_phase", "")
    out = []
    for r in s.get("_sr_pool", []):
        kline = r["kline"]
        today = kline.iloc[-1]
        drop_pct = abs(float(today["涨跌幅"]))
        score = 0.0
        if r["code"] in main_members: score += 0.3
        if drop_pct > 5:               score += 0.3
        if emotion == "divergence":    score += 0.2
        if len(kline) >= 6:
            avg_vol = float(kline["成交量"].iloc[-6:-1].mean())
            if float(today["成交量"]) < avg_vol: score += 0.2
        out.append({"code": r["code"], "_score": round(score, 2),
                    "drop_pct": drop_pct})
    out.sort(key=lambda x: -x["_score"])
    return {"_sr_scored": out}


def sr_rank(s) -> dict:
    return {"candidates": [{
        "code": r["code"],
        "name": "",
        "pattern_id": "S2_setback_reversal",
        "score": float(r["_score"]),
        "reason": f"首阴反包候选·跌幅{r['drop_pct']:.1f}%",
        "suggested_position": 0.05,
    } for r in s.get("_sr_scored", [])[:5]]}


def build_sr_subgraph():
    g = StateGraph(SetbackReversalState)
    g.add_node("filter", sr_filter)
    g.add_node("score", sr_score)
    g.add_node("rank", sr_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
