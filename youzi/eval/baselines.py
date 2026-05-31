from __future__ import annotations

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class NoTradePolicy:
    """floor 基线:永远空仓。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return DecisionPackage(date=state.date, no_trade_reason="baseline:no-trade")


class HighestBoardPolicy:
    """floor 基线:无脑追当日最高连板(超短最朴素的追高)。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        ups = universe.by_status("limit_up")
        if not ups:
            return DecisionPackage(date=state.date, no_trade_reason="无涨停")
        top = max((s.boards or 0) for s in ups)
        if top == 0:
            return DecisionPackage(date=state.date, no_trade_reason="无有效连板数据")
        picks = [s for s in ups if (s.boards or 0) == top]
        cands = [Candidate(code=s.code, name=s.name, pattern="highest_board",
                           reason=f"{s.boards}板最高") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)
