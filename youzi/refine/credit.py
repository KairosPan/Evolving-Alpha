from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youzi.eval.oracle import SCORE
from youzi.eval.trajectory import Trajectory
from youzi.harness.harness import HarnessState
from youzi.harness.skill import Skill

UNATTRIBUTED = "__unattributed__"


class SkillCredit(BaseModel):
    """本次 trajectory 对某技能(或 unattributed 桶)的增量信用汇总(frozen)。"""
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int
    wins: int
    losses: int
    nukes: int
    hit_rate: float
    nuke_rate: float
    expectancy: float


class CreditReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = Field(default_factory=dict)
    unattributed: SkillCredit | None = None
    n_scored: int = 0

    def __bool__(self) -> bool:
        return True


def resolve_skill(pattern: str, harness: HarnessState) -> Skill | None:
    """pattern → Skill:先 skill_id 精确,再 name_cn 精确(多命中取第一个);都不中 → None。"""
    if not pattern:
        return None
    s = harness.skills.get(pattern)
    if s is not None:
        return s
    for sk in harness.skills.all():
        if sk.name_cn == pattern:
            return sk
    return None


def _classify(outcome: str) -> tuple[bool, float, bool]:
    """oracle outcome → (是否 win, SCORE, 是否 nuked)。单一分类源:SCORE/归类规则变动只改这里。"""
    return outcome == "continued", SCORE[outcome], outcome == "nuked"


class _Acc:
    __slots__ = ("n", "wins", "losses", "nukes", "score_sum")

    def __init__(self) -> None:
        self.n = 0
        self.wins = 0
        self.losses = 0
        self.nukes = 0
        self.score_sum = 0.0

    def add(self, oc: str) -> None:
        win, score, nuked = _classify(oc)
        self.n += 1
        self.score_sum += score
        if win:
            self.wins += 1
        else:
            self.losses += 1
        if nuked:
            self.nukes += 1

    def to_credit(self, skill_id: str) -> SkillCredit:
        return SkillCredit(skill_id=skill_id, n=self.n, wins=self.wins,
                           losses=self.losses, nukes=self.nukes,
                           hit_rate=self.wins / self.n, nuke_rate=self.nukes / self.n,
                           expectancy=self.score_sum / self.n)


def apply_credit(traj: Trajectory, harness: HarnessState, decay: float = 0.1) -> CreditReport:
    """对已打分轨迹做信用分配:就地更新被引用技能的 SkillStats(观测,不入 EditLog),返回本次增量汇总。

    契约:对一条 trajectory **调用一次**;重复调用会重复计入(stats 设计为累计)。
    防火墙:输入是走完轨迹的已实现结果,纯事后分析,不回灌 ≤t 推理。
    """
    per: dict[str, _Acc] = {}
    unattr = _Acc()
    n_scored = 0
    for step in traj.scored_steps():                  # 按 step 顺序=决策日序,忠实 ewma 衰减
        for code, sc in step.outcomes.items():
            n_scored += 1
            skill = resolve_skill(sc.pattern, harness)
            if skill is None:
                unattr.add(sc.outcome)                # 未匹配:进 unattributed,不动技能 stats
                continue
            win, score, nuked = _classify(sc.outcome)
            skill.stats.record(win, decay)            # 更新 n/wins/losses/ewma
            m = skill.stats.expectancy if skill.stats.expectancy is not None else 0.0
            skill.stats.expectancy = m + (score - m) / skill.stats.n  # Welford 累计均值
            if nuked:
                skill.stats.nukes += 1
            per.setdefault(skill.skill_id, _Acc()).add(sc.outcome)
    return CreditReport(
        per_skill={sid: acc.to_credit(sid) for sid, acc in per.items()},
        unattributed=unattr.to_credit(UNATTRIBUTED) if unattr.n else None,
        n_scored=n_scored,
    )
