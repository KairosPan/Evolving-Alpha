from __future__ import annotations

import json
from datetime import date as Date

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.universe.universe import CandidateUniverse


def _extract_json(raw: str) -> str:
    """去 markdown 围栏 / 取第一个 { 到最后一个 } 的子串。"""
    # TODO Phase-1b: prose 或 thinking blob 在 JSON 前会让 first-{-to-last-} 失败(目前安全兜底为空仓);后续改贪婪 json 扫描
    s = (raw or "").strip()
    if "```" in s:
        # 去掉 ```json ... ``` 围栏
        s = s.replace("```json", "```").split("```")[1] if s.count("```") >= 2 else s
        s = s.strip()
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j != -1 and j > i:
        return s[i:j + 1]
    return s


def _clamp01(v: object, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, f))


def _match_code(raw_code: object, universe: CandidateUniverse):
    code = (str(raw_code) if raw_code is not None else "").strip()
    if not code:
        return None
    return universe.get(code) or universe.get(code.zfill(6))


def parse_decision(raw: str, date: Date, universe: CandidateUniverse) -> DecisionPackage:
    """把 LLM 文本鲁棒解析成 DecisionPackage:幻觉 code 丢弃,malformed → 空仓兜底。"""
    try:
        data = json.loads(_extract_json(raw))
        if not isinstance(data, dict):
            raise ValueError("顶层非对象")
    except (json.JSONDecodeError, ValueError, IndexError):
        return DecisionPackage(date=date, no_trade_reason="LLM 输出解析失败")

    cands: list[Candidate] = []
    seen: set[str] = set()
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        snap = _match_code(c.get("code"), universe)
        if snap is None or snap.code in seen:        # 幻觉/不在候选池/重复 → 丢
            continue
        seen.add(snap.code)
        cands.append(Candidate(
            code=snap.code, name=snap.name,
            pattern=str(c.get("pattern") or ""), reason=str(c.get("reason") or ""),
            confidence=_clamp01(c.get("confidence", 0.5))))
    return DecisionPackage(date=date, candidates=cands,
                           no_trade_reason=str(data.get("no_trade_reason") or ""))
