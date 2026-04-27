"""二进三 / 分歧三板 sub-graph."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import ContinuousState


def con_filter(s: ContinuousState) -> dict:
    ztb = s.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"_con_pool": []}
    df = ztb.copy()
    df["代码"] = df["代码"].astype(str)
    df = df[df["连板数"].isin([2, 3])]
    return {"_con_pool": df.to_dict("records")}


def con_score(s) -> dict:
    main = (s.get("themes") or {}).get(s.get("main_theme") or "")
    main_members = set((main or {}).get("members", []))
    # Same-theme ladder size
    ladder = sum(1 for r in s.get("_con_pool", []) if str(r["代码"]) in main_members)
    out = []
    for r in s.get("_con_pool", []):
        score = 0.0
        if str(r["代码"]) in main_members: score += 0.4
        if int(r["连板数"]) == 2:           score += 0.2
        if int(r.get("炸板次数", 0)) == 0:  score += 0.2
        if ladder >= 3:                     score += 0.2
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_con_scored": out}


def con_rank(s) -> dict:
    return {"candidates": [{
        "code": str(r["代码"]),
        "name": str(r.get("名称", "")),
        "pattern_id": "first_to_continuous",
        "score": float(r["_score"]),
        "reason": f"{int(r['连板数'])}板·主线·封单{float(r.get('封单金额',0))/1e8:.1f}亿",
        "suggested_position": 0.10,
        "consec_boards": int(r["连板数"]),
    } for r in s.get("_con_scored", [])[:5]]}


def build_con_subgraph():
    g = StateGraph(ContinuousState)
    g.add_node("filter", con_filter)
    g.add_node("score", con_score)
    g.add_node("rank", con_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
