from __future__ import annotations

from datetime import date as Date

from youzi.eval.decision import DecisionPackage, DecisionPolicy
from youzi.eval.metrics import EvalReport, ScoredCandidate, build_report
from youzi.eval.oracle import SCORE, PoolRecord, outcome
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


class WalkForwardEval:
    """前向回放评测:策略每日决策(≤t 快照),horizon 天后用已实现 pool 成员延迟打分。"""

    def __init__(self, source, start: Date, end: Date, horizon: int = 1) -> None:
        if horizon < 1:
            raise ValueError(f"horizon 必须 >=1, got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon

    def run(self, policy: DecisionPolicy) -> EvalReport:
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        pending: list[tuple[int, DecisionPackage]] = []     # (decision_index, DecisionPackage)
        scored: list[ScoredCandidate] = []
        n_no_trade = 0
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()                                  # ≤t 聚合状态
            universe = build_universe(engine.guarded_source, cursor)  # ≤t 候选(经防火墙)
            record.record(cursor, universe)
            decision = policy.decide(state, universe)
            if not decision.candidates:
                n_no_trade += 1
            pending.append((idx, decision))
            # 延迟打分:决策 j 在 idx >= j+horizon 时,用 days_seen[j+horizon] 的已录成员打分
            remaining: list[tuple[int, DecisionPackage]] = []
            for j, dp in pending:
                if idx >= j + self._horizon:
                    mem = record.get(days_seen[j + self._horizon])
                    assert mem is not None, f"BUG: 交易日 {days_seen[j + self._horizon]} 未录制成员"
                    seen_codes: set[str] = set()
                    for c in dp.candidates:
                        if c.code in seen_codes:
                            continue
                        seen_codes.add(c.code)
                        oc = outcome(c.code, mem)
                        scored.append(ScoredCandidate(
                            decision_date=dp.date, code=c.code, pattern=c.pattern,
                            outcome=oc, score=SCORE[oc]))
                else:
                    remaining.append((j, dp))
            pending = remaining
            idx += 1
            if not engine.step():
                break
        # 余下不足 horizon 的决策不打分(丢弃,未来不足)
        return build_report(scored, n_decisions=idx, n_no_trade=n_no_trade,
                            horizon=self._horizon)
