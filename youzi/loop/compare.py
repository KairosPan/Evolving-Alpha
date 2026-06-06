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
from youzi.loop.inner_loop import InnerLoop, LoopConfig, LoopReport
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
    hch_loop_report: LoopReport | None = None   # HCH 完整环报告(refine_events/breaker_events 明细;诊断"自进化改了啥")

    def __bool__(self) -> bool:
        return True


def compare_harnesses(
    harness_factory: Callable[[], HarnessState],
    source, start: Date, end: Date, *,
    agent_llm_factory: Callable[[], LLMClient],
    refiner_llm_factory: Callable[[], LLMClient],
    store_factory: Callable[[], SnapshotStore],
    loop_config: LoopConfig | None = None,
    refiner_config: RefinerConfig | None = None,
) -> ComparisonReport:
    """四路同窗同 oracle 对比:HCH(自精炼内环)vs Hexpert(冻结种子 H + agent,无 Refiner)
    vs Hmin(HighestBoard / NoTrade)。每路独立 fresh 种子 H + 独立 LLM client(防交叉污染)。"""
    cfg = loop_config or LoopConfig()

    # HCH:自精炼内环
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(),
                     refiner_llm_factory(), cfg, refiner_config)
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory)
    hch_arm = ArmReport(name="HCH", report=hch_eval,
                        n_refines=len(lr.refine_events),
                        n_breaker_trips=len(lr.breaker_events),
                        frozen_from=lr.frozen_from)

    # Hexpert:冻结种子 H + agent(无 Refiner → H 全程不变)
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon)
    hexpert_eval = wf.run(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_arm = ArmReport(name="Hexpert", report=hexpert_eval)

    # Hmin:裸基线(同一 wf 实例可复用:run() 内部每次 new ReplayEngine,无状态残留)
    hmin_hb = ArmReport(name="Hmin_highest", report=wf.run(HighestBoardPolicy()))
    hmin_nt = ArmReport(name="Hmin_notrade", report=wf.run(NoTradePolicy()))

    d_mean = hch_eval.mean_score - hexpert_eval.mean_score
    d_hit = hch_eval.hit_rate - hexpert_eval.hit_rate
    d_nuke = hch_eval.nuke_rate - hexpert_eval.nuke_rate
    return ComparisonReport(
        arms={"HCH": hch_arm, "Hexpert": hexpert_arm,
              "Hmin_highest": hmin_hb, "Hmin_notrade": hmin_nt},
        hch_minus_hexpert_mean_score=d_mean,
        hch_minus_hexpert_hit_rate=d_hit,
        hch_minus_hexpert_nuke_rate=d_nuke,
        hch_beats_hexpert=d_mean > 0,
        hch_loop_report=lr,
    )
