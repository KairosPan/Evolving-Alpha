from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field


class ScoredCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    code: str
    pattern: str
    outcome: str
    score: float


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    mean_score: float


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # 期望分(expectancy)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float]:
    """返回 (hit_rate, nuke_rate, mean_score);空列表全 0。"""
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    return (hits / n, nukes / n, mean)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int) -> EvalReport:
    hit, nuke, mean = _agg(scored)
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in scored:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern: dict[str, PatternStat] = {}
    for pat, items in patterns.items():
        h, _, m = _agg(items)
        by_pattern[pat] = PatternStat(n=len(items), hit_rate=h, mean_score=m)
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade,
                      n_candidates=len(scored), hit_rate=hit, nuke_rate=nuke,
                      mean_score=mean, by_pattern=by_pattern)
