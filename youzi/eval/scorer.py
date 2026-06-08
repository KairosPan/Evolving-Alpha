# youzi/eval/scorer.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from youzi.eval.decision import DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, DayMembership, outcome
from youzi.eval.return_oracle import ReturnOracle


class Scorer(Protocol):
    """把一步成熟决策打分成 code→ScoredCandidate(去重;可丢弃缺数候选)。"""
    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """默认:池成员制 outcome + SCORE[outcome](= 现行为)。entry/exit/source 忽略。"""

    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]:
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=SCORE[oc])
        return out


class ReturnScorer:
    """收益打分:outcome 仍池成员制;score=前向收益;收益 None → 丢弃该候选。"""

    def score_step(self, decision: DecisionPackage, mem: DayMembership,
                   entry_day: Date, exit_day: Date, source) -> dict[str, ScoredCandidate]:
        oracle = ReturnOracle(source)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            ret = oracle.score(c.code, entry_day, exit_day)
            if ret is None:
                continue                                  # 丢弃缺收益候选
            oc = outcome(c.code, mem)
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=ret)
        return out
