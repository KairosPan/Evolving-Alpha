"""Daily-only leader strength + role assignment + succession status."""
from __future__ import annotations

from typing import cast

import pandas as pd

from ..state import LeaderProfile, MarketState, SuccessionStatus


def _seal_billions(seal_amount: float) -> float:
    return float(seal_amount) / 1e8 if seal_amount else 0.0


def _strength(row: dict) -> float:
    consec = int(row.get("连板数", 0))
    seal = _seal_billions(row.get("封单金额", 0))
    early = 10 if str(row.get("首次封板时间", "")) < "10:00" else 0
    blast = int(row.get("炸板次数", 0))
    return consec * 2 + seal + early - blast


def _assign_succession(top_leader: LeaderProfile, consec_top: int) -> SuccessionStatus:
    if not top_leader:
        return "broken"
    if top_leader["consec_boards"] >= 4 and not top_leader["blast_today"]:
        return "healthy"
    if top_leader["consec_boards"] >= 4 and top_leader["blast_today"]:
        return "first_div"
    if top_leader["consec_boards"] < consec_top - 1:
        return "trans"
    return "healthy"


def leader_tracker_node(state: MarketState) -> dict:
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"leader_stack": [], "succession_status": "broken"}
    themes = state.get("themes", {})
    member_to_theme = {m: tn for tn, t in themes.items() for m in t.get("members", [])}

    leaders: list[LeaderProfile] = []
    # Per-theme top picks
    for tname, t in themes.items():
        members = t.get("members", [])
        sub = ztb[ztb["代码"].astype(str).isin(members)].copy()
        if sub.empty:
            continue
        sub["_score"] = sub.apply(lambda r: _strength(r), axis=1)
        sub = sub.sort_values("_score", ascending=False)
        for i, (_, row) in enumerate(sub.iterrows()):
            role = "total" if i == 0 else "companion" if i == 1 else "complement"
            leaders.append(cast(LeaderProfile, {
                "code": str(row["代码"]),
                "name": str(row["名称"]),
                "consec_boards": int(row["连板数"]),
                "role": role,
                "sealed_amount": _seal_billions(row.get("封单金额", 0)),
                "blast_today": int(row.get("炸板次数", 0)) > 0,
                "div_count": 0,
            }))

    # Sort overall by score, "total" of the strongest theme is the market leader
    leaders.sort(key=lambda l: -(l["consec_boards"] * 2 + l["sealed_amount"]))
    top = leaders[0] if leaders else None
    succession = _assign_succession(top, state.get("consec_top", 0)) if top else "broken"
    return {"leader_stack": leaders, "succession_status": succession}
