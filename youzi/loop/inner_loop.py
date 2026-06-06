# youzi/loop/inner_loop.py
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, PoolRecord, outcome
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.manager import HarnessManager
from youzi.llm.client import LLMClient
from youzi.refine.credit import apply_credit, merge_credit_reports
from youzi.refine.refiner import RefineReport, Refiner, RefinerConfig
from youzi.refine.signatures import extract_signatures
from youzi.replay.engine import ReplayEngine
from youzi.universe.universe import build_universe


class LoopConfig(BaseModel):
    horizon: int = 1                  # 延迟打分窗口(同 WalkForwardEval)
    refine_every: int = 1             # 每 N 交易日 refine 一次(默认每日)
    credit_window: int = 10           # 给 refiner 的证据窗口(最近 N 个已评分步)
    breaker_window: int = 20          # 滚动 expectancy 窗口(最近 N 个已评分候选)
    baseline_window: int = 20         # 基线 = 前 N 个已评分候选均值
    floor_abs: float = -0.2           # 绝对地板:rolling < floor_abs → 熔断
    floor_rel_margin: float = 0.15    # 相对地板:rolling < baseline - margin → 熔断
    breaker_min_samples: int = 40     # 已评分候选数 >= 此值才可能熔断


class RefineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None
    report: RefineReport


class BreakerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float
    baseline: float | None
    reason: str
    rolled_back_to: int | None


class LoopReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None
    n_edits: int = 0

    def __bool__(self) -> bool:
        return True


class InnerLoop:
    """内环编排:交错 act→延迟打分→在线信用→(每日)refine,reset-free + 能力地板熔断。

    持有 HarnessManager(live H + EditLog + MetaTools + SnapshotStore);
    agent/refiner 由 manager.harness/manager.tools 构造,rollback 后 _rebind 重建。
    """

    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient,
                 config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None) -> None:
        self._mgr = manager
        self._source = source
        self._start = start
        self._end = end
        self._agent_llm = agent_llm
        self._refiner_llm = refiner_llm
        self._cfg = config or LoopConfig()
        self._refiner_cfg = refiner_config or RefinerConfig()
        self._rebind()

    def _rebind(self) -> None:
        """(重)绑定 agent/refiner 到 manager 当前的 harness/tools——启动与 rollback 后调用。"""
        self._agent = LLMAgentPolicy(self._mgr.harness, self._agent_llm)
        self._refiner = Refiner(self._mgr.harness, self._refiner_llm,
                                self._mgr.tools, self._refiner_cfg)

    def run(self) -> LoopReport:
        cfg = self._cfg
        engine = ReplayEngine(self._source, self._start, self._end)
        record = PoolRecord()
        days_seen: list[Date] = []
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list = []
        scores: list[float] = []
        refine_events: list[RefineEvent] = []
        breaker_events: list[BreakerEvent] = []
        last_ckpt: int | None = None
        frozen = False
        frozen_from: Date | None = None
        idx = 0
        while True:
            cursor = engine.cursor
            days_seen.append(cursor)
            state = engine.observe()
            universe = build_universe(engine.guarded_source, cursor)
            record.record(cursor, universe)
            decision = self._agent.decide(state, universe)
            entries: dict[str, EntrySnap] = {}
            for c in decision.candidates:
                if c.code in entries:
                    continue
                snap = universe.get(c.code)
                if snap is not None:
                    entries[c.code] = EntrySnap(code=c.code, status=snap.status, boards=snap.boards)
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "scored": False, "outcomes": {}})
            pending.append(idx)
            newly: list[TrajectoryStep] = []
            remaining: list[int] = []
            for j in pending:
                if idx >= j + cfg.horizon:
                    mem = record.get(days_seen[j + cfg.horizon])
                    assert mem is not None, f"BUG: {days_seen[j + cfg.horizon]} 未录成员"
                    dp = drafts[j]["decision"]
                    seen: set[str] = set()
                    outcomes: dict[str, ScoredCandidate] = {}
                    for c in dp.candidates:
                        if c.code in seen:
                            continue
                        seen.add(c.code)
                        oc = outcome(c.code, mem)
                        outcomes[c.code] = ScoredCandidate(decision_date=dp.date, code=c.code,
                                                           pattern=c.pattern, outcome=oc, score=SCORE[oc])
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    remaining.append(j)
            pending = remaining
            for step in newly:
                cr = apply_credit(Trajectory(steps=[step], horizon=cfg.horizon), self._mgr.harness)
                per_step_credits.append(cr)
                for sc in step.outcomes.values():
                    scores.append(sc.score)
            # 能力地板熔断(自相对 + 绝对;只触发一次)
            if not frozen and len(scores) >= cfg.breaker_min_samples:
                baseline = sum(scores[:cfg.baseline_window]) / cfg.baseline_window
                window = scores[-cfg.breaker_window:]
                rolling = sum(window) / len(window)
                reason: str | None = None
                if rolling < cfg.floor_abs:
                    reason = "rolling<floor_abs"
                elif rolling < baseline - cfg.floor_rel_margin:
                    reason = "rolling<baseline-margin"
                if reason is not None:
                    rolled: int | None = None
                    if last_ckpt is not None:
                        self._mgr.rollback_to(last_ckpt)
                        self._rebind()
                        rolled = last_ckpt
                    frozen = True
                    frozen_from = cursor
                    breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=baseline,
                                                       reason=reason, rolled_back_to=rolled))
            # 每日 refine(未冻结 + 有新证据 + 到节奏)
            if not frozen and newly and (idx % cfg.refine_every == 0):
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                last_ckpt = ver
                win = scored_steps[-cfg.credit_window:]
                win_traj = Trajectory(steps=win, horizon=cfg.horizon)
                credit = merge_credit_reports(per_step_credits[-cfg.credit_window:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
            idx += 1
            if not engine.step():
                break
        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts], horizon=cfg.horizon)
        return LoopReport(trajectory=traj, refine_events=refine_events,
                          breaker_events=breaker_events, frozen_from=frozen_from,
                          n_edits=len(self._mgr.log))
