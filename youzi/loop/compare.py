# youzi/loop/compare.py
from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from youzi.eval.metrics import EvalReport
from youzi.eval.stats import StatVerdict, daily_series, paired_daily_diff, verdict
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
    hch_minus_hexpert_mean_score: float              # 原始分差(保留旧口径)
    hch_minus_hexpert_mean_excess: float = 0.0       # 截面超额差(advantage 口径;旧 JSON 缺省 → 0.0)
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool                          # 北极星裁决:mean_excess>0(C2 起超额口径;旧 bool 保留)
    stat_verdict: StatVerdict | None = None     # C1 统计裁决:日级配对差→CI/p/MDE 四值 verdict(旧 JSON 缺省 → None)
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
    scorer=None,
) -> ComparisonReport:
    """四路同窗同 oracle 对比:HCH(自精炼内环)vs Hexpert(冻结种子 H + agent,无 Refiner)
    vs Hmin(HighestBoard / NoTrade)。每路独立 fresh 种子 H + 独立 LLM client(防交叉污染)。"""
    cfg = loop_config or LoopConfig()

    # HCH:自精炼内环
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(),
                     refiner_llm_factory(), cfg, refiner_config, scorer=scorer)
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory)
    hch_arm = ArmReport(name="HCH", report=hch_eval,
                        n_refines=len(lr.refine_events),
                        n_breaker_trips=len(lr.breaker_events),
                        frozen_from=lr.frozen_from)

    # Hexpert:冻结种子 H + agent(无 Refiner → H 全程不变)
    # C1:走 walk()+report_from_trajectory(与 run() 等价,有等价性测试守着),
    # 留住 Trajectory 供日级统计裁决——不重复跑 LLM。
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer)
    hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_eval = report_from_trajectory(hexpert_traj)
    hexpert_arm = ArmReport(name="Hexpert", report=hexpert_eval)

    # Hmin:裸基线(同一 wf 实例可复用:run() 内部每次 new ReplayEngine,无状态残留)
    hmin_hb = ArmReport(name="Hmin_highest", report=wf.run(HighestBoardPolicy()))
    hmin_nt = ArmReport(name="Hmin_notrade", report=wf.run(NoTradePolicy()))

    d_mean = hch_eval.mean_score - hexpert_eval.mean_score
    d_excess = hch_eval.mean_excess - hexpert_eval.mean_excess   # 截面 demean 砍掉日间共同β
    d_hit = hch_eval.hit_rate - hexpert_eval.hit_rate
    d_nuke = hch_eval.nuke_rate - hexpert_eval.nuke_rate
    # C1 统计裁决:两臂日级等权 advantage 序列 → 按日配对差 → bootstrap CI/置换 p/MDE
    diffs = paired_daily_diff(daily_series(lr.trajectory), daily_series(hexpert_traj))
    stat = verdict(diffs)
    return ComparisonReport(
        arms={"HCH": hch_arm, "Hexpert": hexpert_arm,
              "Hmin_highest": hmin_hb, "Hmin_notrade": hmin_nt},
        hch_minus_hexpert_mean_score=d_mean,
        hch_minus_hexpert_mean_excess=d_excess,
        hch_minus_hexpert_hit_rate=d_hit,
        hch_minus_hexpert_nuke_rate=d_nuke,
        hch_beats_hexpert=d_excess > 0,   # C2:北极星裁决改超额口径(去市场β后才算真胜)
        stat_verdict=stat,                # C1:带 CI/p/MDE 的可证伪裁决(旧 bool 保留向后兼容)
        hch_loop_report=lr,
    )
