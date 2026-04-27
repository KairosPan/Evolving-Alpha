"""State → JSON / Markdown."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd


def state_to_json(state: dict) -> dict:
    """Serialize state to JSON-safe dict, dropping `raw` (contains DataFrames)."""
    def _safe(v: Any) -> Any:
        if isinstance(v, pd.DataFrame):
            return f"<DataFrame {v.shape}>"
        if isinstance(v, dict):
            return {k: _safe(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_safe(x) for x in v]
        return v
    return {k: _safe(v) for k, v in state.items() if k != "raw"}


def render_markdown(state: dict) -> str:
    date = state.get("target_date", "?")
    lines = [f"# 游资策略复盘 · {date}", ""]

    lines += ["## 情绪诊断"]
    lines += [f"- emotion_phase: **{state.get('emotion_phase','?')}**"]
    lines += [f"- 涨停 {state.get('limit_up_count','?')} | "
              f"最高连板 {state.get('consec_top','?')} | "
              f"炸板率 {(state.get('blast_rate', 0) * 100):.1f}%"]
    lines += [f"- 五日线: {state.get('five_day_pos','?')} | "
              f"新周期确立: {'✅' if state.get('is_new_cycle_day') else '❌'}"]
    if state.get("errors"):
        lines += [f"- ⚠️ 节点警告: {len(state['errors'])} 条"]
    lines += [""]

    main = state.get("main_theme")
    themes = state.get("themes", {})
    if main and main in themes:
        t = themes[main]
        lines += ["## 主线", f"**{main}** ({t.get('phase','?')}, "
                            f"score {t.get('resonance_score',0):.2f})"]
        leader = t.get("leader")
        if leader:
            lines += [f"- 龙头: {leader}"]
        members = t.get("members", [])
        if len(members) > 1:
            lines += [f"- 成员: {', '.join(members[:8])}{'…' if len(members) > 8 else ''}"]
        lines += [""]

    plan = state.get("plan", {})
    cands = plan.get("candidates", [])
    if cands:
        lines += [f"## 候选池 ({len(cands)})", "",
                  "| code | name | pattern | score | reason | 仓位 |",
                  "|---|---|---|---|---|---|"]
        for c in cands:
            lines += [f"| {c['code']} | {c.get('name','')} | {c.get('pattern_id','')} "
                      f"| {c.get('score',0):.2f} | {c.get('reason','')} "
                      f"| {c.get('suggested_position',0):.2f} |"]
        lines += [""]
    else:
        lines += ["## 候选池", "(空 / 全部被风控剔除)", ""]

    flags = state.get("risk_flags", [])
    if flags:
        lines += ["## 风控告警"]
        lines += [f"- ⚠️ {f}" for f in flags] + [""]

    arbs = state.get("arb_opportunities", [])
    if arbs:
        lines += ["## 套利机会"]
        for a in arbs:
            lines += [f"- {a['reason']}: {a['code']} {a.get('name','')}"]
        lines += [""]

    lines += ["## 建议总仓位上限",
              f"- 总仓 ≤ {plan.get('position_total_max', 0)*100:.0f}% "
              f"({state.get('emotion_phase','?')} · {state.get('index_phase','?')})"]

    if state.get("errors"):
        lines += ["", "## 节点错误"]
        for e in state["errors"]:
            lines += [f"- {e}"]

    return "\n".join(lines)
