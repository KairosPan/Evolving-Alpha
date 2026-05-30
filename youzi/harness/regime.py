from __future__ import annotations

CANONICAL_PHASES = ["混沌冰点", "修复启动", "情绪回暖", "题材启动", "主升", "震荡补涨", "退潮"]
ECOLOGY_TAGS = ["连板生态", "容量生态", "20cm生态", "次新生态", "超跌生态", "ST生态", "北交生态"]

# 优先级有序:"修复" 必须在 "启动" 之前判定,否则 "修复启动" 会被错归到 题材启动。
_PHASE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("混沌", "冰点"), "混沌冰点"),
    (("修复",), "修复启动"),
    (("回暖",), "情绪回暖"),
    (("题材启动", "启动"), "题材启动"),
    (("主升",), "主升"),
    (("震荡", "补涨"), "震荡补涨"),
    (("退潮",), "退潮"),
]


def classify_regime(raw: str) -> tuple[str, str | None]:
    """归一单个 regime 串。返回 (kind, value),kind ∈ {'phase','ecology','other'}。"""
    s = (raw or "").strip()
    if not s:
        return ("other", None)
    for tag in ECOLOGY_TAGS:
        if tag in s:
            return ("ecology", tag)
    for keywords, phase in _PHASE_RULES:
        if any(k in s for k in keywords):
            return ("phase", phase)
    return ("other", None)


def split_regimes(raw: list[str]) -> tuple[list[str], list[str]]:
    """把 raw applicable_regime 列表归一为 (canonical_phases, ecologies),首见序去重,非相位丢弃。"""
    phases: list[str] = []
    ecologies: list[str] = []
    for item in raw or []:
        kind, value = classify_regime(item)
        if kind == "phase" and value not in phases:
            phases.append(value)
        elif kind == "ecology" and value not in ecologies:
            ecologies.append(value)
    return (phases, ecologies)
