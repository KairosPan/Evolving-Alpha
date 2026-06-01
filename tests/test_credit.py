# tests/test_credit.py
from datetime import date, datetime, time

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.refine.credit import apply_credit, resolve_skill
from youzi.schemas.market import MarketState

_SCORE = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def _state(d, max_board=0):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _skill(sid, name="技能"):
    return Skill(skill_id=sid, name_cn=name, type="pattern",
                 trigger="t", entry="e", exit_stop="s", status="active")


def _harness(skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(skills),
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _step(d, code, pattern, oc, boards, max_board):
    sc = ScoredCandidate(decision_date=d, code=code, pattern=pattern, outcome=oc,
                         score=_SCORE[oc])
    return TrajectoryStep(
        date=d, market=_state(d, max_board),
        decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern=pattern)]),
        entries={code: EntrySnap(code=code, status="limit_up", boards=boards)},
        scored=True, outcomes={code: sc})


def test_resolve_skill_by_id_then_name_then_none():
    h = _harness([_skill("pat_a", "龙头接力")])
    assert resolve_skill("pat_a", h).skill_id == "pat_a"       # by skill_id
    assert resolve_skill("龙头接力", h).skill_id == "pat_a"     # by name_cn
    assert resolve_skill("不存在", h) is None
    assert resolve_skill("", h) is None


def test_apply_credit_updates_stats_and_distinguishes_faded_nuked():
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[
        _step(d0, "X", "pat_a", "continued", 3, 3),
        _step(d1, "Y", "pat_a", "faded", 2, 3),
        _step(d2, "Z", "pat_a", "nuked", 3, 3),
    ], horizon=1)
    rep = apply_credit(traj, h)
    st = h.skills.get("pat_a").stats
    assert st.n == 3 and st.wins == 1 and st.losses == 2 and st.nukes == 1
    assert abs(st.expectancy - 0.0) < 1e-9               # mean(1,0,-1)=0
    # ewma:1.0 → 0.1*0+0.9*1=0.9 → 0.1*0+0.9*0.9=0.81
    assert abs(st.ewma_winrate - 0.81) < 1e-9
    cr = rep.per_skill["pat_a"]
    assert cr.n == 3 and cr.wins == 1 and cr.nukes == 1
    assert abs(cr.hit_rate - 1 / 3) < 1e-9 and abs(cr.expectancy) < 1e-9
    assert rep.n_scored == 3 and rep.unattributed is None


def test_apply_credit_unattributed_bucket():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "无此技能", "nuked", 1, 2)], horizon=1)
    rep = apply_credit(traj, h)
    assert h.skills.get("pat_a").stats.n == 0           # 未匹配 → 不动任何技能
    assert rep.per_skill == {}
    assert rep.unattributed is not None
    assert rep.unattributed.n == 1 and rep.unattributed.nukes == 1


def test_apply_credit_idempotency_doubles():
    d0 = date(2024, 6, 26)
    h = _harness([_skill("pat_a")])
    traj = Trajectory(steps=[_step(d0, "X", "pat_a", "continued", 3, 3)], horizon=1)
    apply_credit(traj, h)
    apply_credit(traj, h)                               # 契约:每条 trajectory 调一次;调两次=累计翻倍
    assert h.skills.get("pat_a").stats.n == 2
