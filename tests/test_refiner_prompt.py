# tests/test_refiner_prompt.py
from datetime import date, datetime
from youzi.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from youzi.refine.credit import CreditReport, SkillCredit
from youzi.refine.signatures import FailureSignature
from youzi.eval.trajectory import Trajectory, TrajectoryStep
from youzi.eval.decision import DecisionPackage, Candidate
from youzi.eval.metrics import ScoredCandidate
from youzi.schemas.market import MarketState
from tests.test_metatools import _harness


def test_system_prompt_k_pass_lists_skill_tools_and_rules():
    p = build_refiner_system_prompt(_harness(), "K")
    assert "write_skill" in p and "promote_skill" in p
    assert "rationale" in p
    assert "immutable" in p or "红线" in p
    assert "ops" in p                                   # 输出契约
    assert "rewrite_doctrine" not in p                  # K-pass 不暴露 doctrine 工具


def test_system_prompt_p_pass_lists_mutable_doctrine():
    p = build_refiner_system_prompt(_harness(), "p")
    assert "rewrite_doctrine" in p
    assert "主升作战" in p                              # mutable 段渲染出来


def test_system_prompt_m_pass_lists_memory_tools():
    p = build_refiner_system_prompt(_harness(), "M")
    assert "process_memory" in p and "demote_memory" in p


def test_user_prompt_renders_evidence():
    mkt = MarketState(date=date(2024, 6, 27), max_board_height=5, limit_up_count=10,
                      blowup_count=3, blowup_rate=0.3, limit_down_count=1, echelon=[],
                      money_effect_raw=1.0, sentiment_raw=0.0, sentiment_norm=0.5,
                      as_of=datetime(2024, 6, 27, 15, 0))
    step = TrajectoryStep(
        date=date(2024, 6, 27), market=mkt,
        decision=DecisionPackage(date=date(2024, 6, 27),
                                 candidates=[Candidate(code="000001", name="平安",
                                                       pattern="接力", reason="r", confidence=0.6)]),
        scored=True,
        outcomes={"000001": ScoredCandidate(decision_date=date(2024, 6, 27), code="000001",
                                            pattern="接力", outcome="nuked", score=-1.0)})
    traj = Trajectory(steps=[step], horizon=1)
    credit = CreditReport(per_skill={"a": SkillCredit(skill_id="a", n=3, wins=0, losses=3,
                                                      nukes=2, hit_rate=0.0, nuke_rate=0.67,
                                                      expectancy=-0.67)}, n_scored=3)
    sigs = [FailureSignature(date=date(2024, 6, 27), code="000001", pattern="接力",
                             skill_id="a", kind="chased_into_nuke", score=-1.0,
                             evidence="boards=5/max=5 → 追最高板被闷")]
    u = build_refiner_user_prompt(traj, credit, sigs, window=10)
    assert "000001" in u and "nuked" in u
    assert "a" in u and "nuke" in u.lower()
    assert "chased_into_nuke" in u and "追最高板被闷" in u
