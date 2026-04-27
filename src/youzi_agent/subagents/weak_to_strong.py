"""弱转强 sub-graph (daily-only approximation)."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import WeakToStrongState


def w2s_filter(s: WeakToStrongState) -> dict:
    yest = s.get("raw", {}).get("ztb_yesterday")
    today = s.get("raw", {}).get("ztb_today")
    if yest is None or today is None or len(today) == 0:
        return {"_w2s_pool": []}
    yest_codes = yest[yest.get("炸板次数", 0).astype(int) >= 2]["代码"].astype(str).tolist()
    sub = today[today["代码"].astype(str).isin(yest_codes)].copy()
    if sub.empty:
        return {"_w2s_pool": []}
    if "开盘价" in sub.columns and "昨日收盘" in sub.columns:
        sub = sub[(sub["开盘价"] / sub["昨日收盘"]) > 1.05]
    if "涨停价" in sub.columns and "开盘价" in sub.columns:
        sub = sub[sub["开盘价"] < sub["涨停价"] * 0.999]   # 排除一字开
    return {"_w2s_pool": sub.to_dict("records")}


def w2s_score(s) -> dict:
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    out = []
    for r in s.get("_w2s_pool", []):
        score = 0.0
        if str(r["代码"]) in main_members: score += 0.4
        if str(r.get("首次封板时间", "")) < "09:35": score += 0.3   # 5min 秒板
        if float(r.get("封单金额", 0)) > 1e8: score += 0.2
        if int(r.get("炸板次数", 0)) == 0:    score += 0.1
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_w2s_scored": out}


def w2s_rank(s) -> dict:
    return {"candidates": [{
        "code": str(r["代码"]),
        "name": str(r.get("名称", "")),
        "pattern_id": "L2_weak_to_strong",
        "score": float(r["_score"]),
        "reason": f"昨烂今强·{r.get('首次封板时间','')}秒板·封单{float(r.get('封单金额',0))/1e8:.1f}亿",
        "suggested_position": 0.10,
    } for r in s.get("_w2s_scored", [])[:5]]}


def build_w2s_subgraph():
    g = StateGraph(WeakToStrongState)
    g.add_node("filter", w2s_filter)
    g.add_node("score", w2s_score)
    g.add_node("rank", w2s_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
