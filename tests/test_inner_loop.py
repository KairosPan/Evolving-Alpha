# tests/test_inner_loop.py
from datetime import date, timedelta

import pandas as pd
import pytest

from youzi.eval.trajectory import Trajectory
from youzi.loop.inner_loop import InnerLoop, LoopConfig, LoopReport, RefineEvent, BreakerEvent
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource


def _seed_h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "longtou", "name_cn": "龙头接力", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "持有龙头"})])
    return HarnessState(doctrine=doc, skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _mgr(tmp_path):
    return HarnessManager(_seed_h(), SnapshotStore(tmp_path))


def _decision(code):
    return ('{"candidates": [{"code": "%s", "pattern": "龙头接力", "confidence": 0.7}],'
            ' "no_trade_reason": ""}') % code


def _loop(tmp_path, src, agent_scripts, refiner_scripts, config=None):
    mgr = _mgr(tmp_path)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient(agent_scripts), MockLLMClient(refiner_scripts),
                     config=config), mgr


def test_models_frozen_and_truthy():
    rep = LoopReport(trajectory=Trajectory())
    assert bool(rep) is True
    with pytest.raises(Exception):
        rep.frozen_from = date(2024, 1, 1)        # frozen


def test_loop_constructs_and_rebinds(tmp_path):
    src = FakeSource({("zt", date(2024, 6, 26)): pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [1]})},
                     [date(2024, 6, 26)])
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'])
    # 构造后 agent/refiner 已绑定到 mgr.harness
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    # rollback 后 _rebind 指向还原态新对象
    v = mgr.checkpoint("c0")
    mgr.tools.retire_skill("longtou")
    mgr.rollback_to(v)
    loop._rebind()
    assert loop._agent._harness is mgr.harness
    assert loop._refiner._h is mgr.harness
    assert mgr.harness.skills.get("longtou").status == "active"   # 还原


def _continued_src():
    """A 每日涨停(continued);3 日。"""
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {}
    for d in days:
        frames[("zt", d)] = pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]})
    return FakeSource(frames, days)


def test_run_interleaves_scoring_and_online_credit(tmp_path):
    src = _continued_src()
    loop, mgr = _loop(tmp_path, src, [_decision("A")], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_samples=10_000))  # 不熔断
    rep = loop.run()
    # 轨迹:3 步,前 2 步已打分(horizon=1),尾步未打分
    assert rep.trajectory.n_decisions() == 3
    assert [s.date for s in rep.trajectory.scored_steps()] == [date(2024, 6, 26), date(2024, 6, 27)]
    assert rep.trajectory.steps[2].scored is False
    assert rep.trajectory.steps[0].outcomes["A"].outcome == "continued"
    # 在线信用:技能 longtou(pattern "龙头接力")被引用且 continued → stats 在 H 内已更新
    st = mgr.harness.skills.get("longtou").stats
    assert st.n == 2 and st.wins == 2          # 2 个已打分决策都归因到 longtou 且 continued


def test_refine_edits_visible_next_day_resetfree(tmp_path):
    src = _continued_src()
    # refiner:refine1 在 K-pass 退役 longtou;p/M 空;之后全空(MockLLM 重复末元素)
    refiner_scripts = ['{"ops": []}',
                       '{"ops": [{"tool": "retire_skill", "args": {"skill_id": "longtou"},'
                       ' "rationale": "示例退役"}]}',
                       '{"ops": []}']
    loop, mgr = _loop(tmp_path, src, [_decision("A")], refiner_scripts,
                      config=LoopConfig(breaker_min_samples=10_000))  # 不熔断
    # 退役证据门(Phase-1b-3d):day1 refine 时 longtou 仅累计 n=1<默认门槛,会被拦下;
    # 本测试意在验证退役的 reset-free 可见性,故预置足够样本让其过门。
    mgr.harness.skills.get("longtou").stats.n = 5
    rep = loop.run()
    # refine 每日触发(有新证据起):day1、day2 各一次
    assert [e.date for e in rep.refine_events] == [date(2024, 6, 27), date(2024, 6, 28)]
    assert rep.refine_events[0].checkpoint_version is not None
    # reset-free:day1 决策(call#1)系统提示仍含 longtou;day2(call#2)已不含(退役于 day1 refine 后)
    sys_day1 = loop._agent_llm.calls[1][0]
    sys_day2 = loop._agent_llm.calls[2][0]
    assert "龙头接力" in sys_day1
    assert "龙头接力" not in sys_day2
    # 编辑入 EditLog(带 rationale)
    assert any(r.tool == "retire_skill" and r.rationale for r in mgr.log.records())


def _nuke_src(n_days):
    """每日 C_i 涨停;次日 C_i 跌停(被选后必 nuked)。"""
    days = [date(2024, 6, 1) + timedelta(days=k) for k in range(n_days)]
    frames = {}
    for i, d in enumerate(days):
        frames[("zt", d)] = pd.DataFrame({"code": [f"C{i}"], "name": [f"C{i}"], "boards": [1]})
        if i >= 1:
            frames[("dt", d)] = pd.DataFrame({"code": [f"C{i-1}"], "name": [f"C{i-1}"]})
    return FakeSource(frames, days)


def test_breaker_trips_rolls_back_and_freezes(tmp_path):
    n = 8
    src = _nuke_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]    # 每日选当日涨停 C_i
    cfg = LoopConfig(breaker_window=2, baseline_window=2, breaker_min_samples=3,
                     floor_abs=-0.5, refine_every=1)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    # 每个被选 code 次日跌停 → 全 nuked(-1)→ rolling 跌破 floor_abs(-0.5)→ 熔断
    assert len(rep.breaker_events) == 1
    be = rep.breaker_events[0]
    assert be.reason == "rolling<floor_abs"          # floor_abs=-0.5, rolling=-1.0 → 确定走绝对地板分支
    assert be.rolled_back_to is not None          # 熔断前已有 refine → 有 checkpoint
    assert rep.frozen_from == be.date
    # 冻结后不再有 refine
    assert all(e.date < rep.frozen_from for e in rep.refine_events)


def test_breaker_freezes_without_checkpoint_when_no_refine(tmp_path):
    n = 6
    src = _nuke_src(n)
    agent_scripts = [_decision(f"C{i}") for i in range(n)]
    # refine_every 极大 → 永不 refine → 熔断时无 checkpoint
    cfg = LoopConfig(breaker_window=2, baseline_window=2, breaker_min_samples=3,
                     floor_abs=-0.5, refine_every=10_000)
    loop, mgr = _loop(tmp_path, src, agent_scripts, ['{"ops": []}'], config=cfg)
    rep = loop.run()
    assert len(rep.breaker_events) == 1
    assert rep.breaker_events[0].rolled_back_to is None       # 无 checkpoint → 只冻结
    assert rep.refine_events == []


def test_loop_config_rejects_degenerate():
    from pydantic import ValidationError
    for bad in ({"horizon": 0}, {"breaker_window": 0}, {"baseline_window": 0},
                {"breaker_min_samples": 0}, {"refine_every": 0}, {"credit_window": 0}):
        with pytest.raises(ValidationError):
            LoopConfig(**bad)


def test_inner_loop_accepts_return_scorer(tmp_path):
    from youzi.eval.scorer import ReturnScorer
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W"], "name": ["赢家"], "boards": [2]}) for d in days}
    ohlcv = {"W": pd.DataFrame([(date(2024, 6, 27), 10.0, 11, 9, 10.5, 100),
                                (date(2024, 6, 28), 10.6, 12, 10, 11.0, 200)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    src = FakeSource(frames, days, ohlcv=ohlcv)
    mgr = _mgr(tmp_path)
    loop = InnerLoop(mgr, src, days[0], days[-1], MockLLMClient(_decision("W")),
                     MockLLMClient('{"ops": []}'),
                     config=LoopConfig(horizon=1, breaker_min_samples=10_000),
                     scorer=ReturnScorer())
    rep = loop.run()
    # 决策 6/26 → entry=exit=6/27:(10.5−10)/10=+0.05;score 为收益
    sc = rep.trajectory.scored_steps()[0].outcomes["W"]
    assert sc.outcome == "continued" and abs(sc.score - 0.05) < 1e-9


def test_refine_skips_zero_evidence_no_trade_days(tmp_path):
    # 冰点:zt 池空、agent 空仓 → 所有已评分步 outcomes={} → 不应触发 refine(省 LLM/磁盘)
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame() for d in days}
    src = FakeSource(frames, days)
    no_trade = '{"candidates": [], "no_trade_reason": "冰点空仓"}'
    loop, mgr = _loop(tmp_path, src, [no_trade], ['{"ops": []}'],
                      config=LoopConfig(breaker_min_samples=10_000))
    rep = loop.run()
    assert rep.trajectory.n_no_trade() == 3
    assert rep.refine_events == []                # 零证据 → 不 refine
    assert loop._refiner_llm.calls == []          # refiner LLM 从未被调
