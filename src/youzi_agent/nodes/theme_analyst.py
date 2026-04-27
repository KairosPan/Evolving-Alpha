"""Cluster today's limit-up stocks into themes (LLM with rule fallback)."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from ..llm.deepseek import get_llm
from ..llm.schemas import ThemeAnalystOut
from ..state import MarketState

THEME_PROMPT = """你是 A 股游资策略师。给定今日涨停股票池及其行业 / 概念标签,完成 4 件事:
1) 把股票按"今日真正驱动的题材"重新聚类(同一只股可属多个题材)
2) 判每个题材的演绎阶段:budding(萌芽) / horizontal(横向扩散) / vertical(纵向涨停加速) / switching(切换中) / exhausted(衰竭)
3) 推断当日主线 main_theme(若无明显主线返回 null)
4) 判 theme_axis:horizontal=多线开花 / vertical=单线纵深 / switching=主线切换 / exhausted=全面衰竭

# 今日涨停股
{lu_table}

# 上下文
- 当日涨停家数: {lu_count}
- 最高连板: {consec_top}
- 情绪值锚定: {sentiment_value}

只输出 JSON,严格符合 schema。"""


def _render_lu_table(ztb: pd.DataFrame) -> str:
    cols = [c for c in ["代码", "名称", "连板数", "所属行业", "概念"] if c in ztb.columns]
    return ztb[cols].to_string(index=False) if cols else "(空)"


def _rule_fallback(state: MarketState) -> dict:
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return {"themes": {}, "main_theme": None, "theme_axis": "horizontal"}
    group_col = "所属行业" if "所属行业" in ztb.columns else ("概念" if "概念" in ztb.columns else None)
    if not group_col:
        return {"themes": {"_unclassified": {
            "name": "_unclassified",
            "members": ztb["代码"].astype(str).tolist(),
            "leader": None, "catalysts": [], "phase": "horizontal", "resonance_score": 0.3,
        }}, "main_theme": None, "theme_axis": "horizontal"}
    buckets: dict[str, list[str]] = defaultdict(list)
    for _, row in ztb.iterrows():
        buckets[str(row[group_col])].append(str(row["代码"]))
    themes = {name: {
        "name": name, "members": members,
        "leader": members[0] if members else None,
        "catalysts": [], "phase": "horizontal",
        "resonance_score": min(1.0, len(members) / 5),
    } for name, members in buckets.items()}
    main = max(buckets.items(), key=lambda kv: len(kv[1]))[0] if buckets else None
    axis = "vertical" if main and len(buckets[main]) >= 5 else "horizontal"
    return {"themes": themes, "main_theme": main, "theme_axis": axis}


def theme_analyst_node(state: MarketState) -> dict:
    if not state.get("use_llm", True):
        return _rule_fallback(state)
    ztb = state.get("raw", {}).get("ztb_today")
    if ztb is None or len(ztb) == 0:
        return _rule_fallback(state)
    try:
        llm = get_llm(0.3).with_structured_output(ThemeAnalystOut)
        out = llm.invoke(THEME_PROMPT.format(
            lu_table=_render_lu_table(ztb),
            lu_count=state.get("limit_up_count", 0),
            consec_top=state.get("consec_top", 0),
            sentiment_value=state.get("sentiment_value", 0),
        ))
        return {
            "themes": {t.model_dump()["name"]: t.model_dump() for t in out.themes},
            "main_theme": out.main_theme,
            "theme_axis": out.theme_axis,
        }
    except Exception as e:
        return {"errors": [f"theme_analyst LLM failed: {e}"], **_rule_fallback(state)}
