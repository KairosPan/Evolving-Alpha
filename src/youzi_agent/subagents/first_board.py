"""一进二 sub-graph: filter → score → rank."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import FirstBoardState


def fb_filter(s: FirstBoardState) -> dict:
    ztb_yest = s.get("raw", {}).get("ztb_yesterday")
    if ztb_yest is None or len(ztb_yest) == 0:
        return {"_fb_pool": []}
    df = ztb_yest.copy()
    df["代码"] = df["代码"].astype(str)
    df = df[df["连板数"] == 1]
    if "名称" in df.columns:
        df = df[~df["名称"].astype(str).str.contains("ST|退", na=False)]
    if "上市天数" in df.columns:
        df = df[df["上市天数"] > 60]
    if "开盘价" in df.columns and "涨停价" in df.columns:
        df = df[df["开盘价"] < df["涨停价"] * 0.999]
    return {"_fb_pool": df.to_dict("records")}


def fb_score(s) -> dict:
    pool = s.get("_fb_pool", [])
    main_members = set(((s.get("themes") or {}).get(s.get("main_theme") or "") or {}).get("members", []))
    out = []
    for r in pool:
        score = 0.0
        if str(r.get("代码")) in main_members: score += 0.4
        if float(r.get("封单金额", 0)) > 1e8:   score += 0.2
        if str(r.get("首次封板时间", "")) < "10:00": score += 0.2
        if int(r.get("炸板次数", 0)) == 0:      score += 0.2
        out.append({**r, "_score": round(score, 2)})
    out.sort(key=lambda x: -x["_score"])
    return {"_fb_scored": out}


def fb_rank(s) -> dict:
    scored = s.get("_fb_scored", [])[:5]
    candidates = []
    for r in scored:
        candidates.append({
            "code": str(r["代码"]),
            "name": str(r.get("名称", "")),
            "pattern_id": "L1_first_board",
            "score": float(r["_score"]),
            "reason": f"昨首板·封单{float(r.get('封单金额', 0))/1e8:.1f}亿·封板{r.get('首次封板时间','')}",
            "suggested_position": 0.10,
        })
    return {"candidates": candidates}


def build_fb_subgraph():
    g = StateGraph(FirstBoardState)
    g.add_node("filter", fb_filter)
    g.add_node("score", fb_score)
    g.add_node("rank", fb_rank)
    g.add_edge(START, "filter")
    g.add_edge("filter", "score")
    g.add_edge("score", "rank")
    g.add_edge("rank", END)
    return g.compile()
