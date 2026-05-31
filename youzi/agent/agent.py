from __future__ import annotations

from youzi.agent.parse import parse_decision
from youzi.agent.prompt import build_system_prompt, build_user_prompt
from youzi.eval.decision import DecisionPackage
from youzi.harness.harness import HarnessState
from youzi.llm.client import LLMClient
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class LLMAgentPolicy:
    """LLM 驱动的 DecisionPolicy:harness 包住模型,读盘面+候选→决策包。

    持有 harness 而非预渲染提示:每次 decide 按当前 H 重建系统提示,
    使 Phase-1b 的 Refiner 改 H 后立即对 agent 可见。
    """

    def __init__(self, harness: HarnessState, llm: LLMClient) -> None:
        self._harness = harness
        self._llm = llm

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness)
        user = build_user_prompt(state, universe)
        raw = self._llm.complete(system, user)
        return parse_decision(raw, state.date, universe)
