from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class Candidate(BaseModel):
    """策略选出的一个候选标的(v1 评测只看选了哪些 code + 声明的模式)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    name: str = ""
    pattern: str = ""              # 命中的模式/skill_id(策略声明,用于 by_pattern 归因)
    reason: str = ""
    confidence: float = 0.5


class DecisionPackage(BaseModel):
    """某交易日的决策包(co-pilot 输出的 v1 子集:候选池 + 不参与理由)。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""


class DecisionPolicy(Protocol):
    """策略接口:读当日聚合状态 + 候选 universe,产决策包。

    LLM Agent(Phase-1)在构造期持有 HarnessState/LLM,decide 仍只吃 (state, universe)。
    """
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
