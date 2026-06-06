# youzi/loop/compare.py
from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from youzi.eval.metrics import EvalReport
from youzi.eval.walk_forward import WalkForwardEval, report_from_trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.manager import HarnessManager
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import LLMClient
from youzi.loop.inner_loop import InnerLoop, LoopConfig
from youzi.refine.refiner import RefinerConfig


class ArmReport(BaseModel):
    """一路对比的结果(frozen)。HCH 额外带环信息。"""
    model_config = ConfigDict(frozen=True)
    name: str
    report: EvalReport
    n_refines: int | None = None         # 仅 HCH:refine 次数
    n_breaker_trips: int | None = None   # 仅 HCH:熔断次数
    frozen_from: Date | None = None      # 仅 HCH:熔断冻结起始日


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)
    hch_minus_hexpert_mean_score: float
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool

    def __bool__(self) -> bool:
        return True
