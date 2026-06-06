# tests/test_compare.py
import pytest

from youzi.loop.compare import ArmReport, ComparisonReport
from youzi.eval.metrics import EvalReport


def _empty_eval():
    return EvalReport(n_decisions=0, n_no_trade=0, n_candidates=0,
                      hit_rate=0.0, nuke_rate=0.0, mean_score=0.0)


def test_models_frozen_and_truthy():
    arm = ArmReport(name="HCH", report=_empty_eval(), n_refines=3,
                    n_breaker_trips=0, frozen_from=None)
    cr = ComparisonReport(arms={"HCH": arm},
                          hch_minus_hexpert_mean_score=0.0,
                          hch_minus_hexpert_hit_rate=0.0,
                          hch_minus_hexpert_nuke_rate=0.0,
                          hch_beats_hexpert=False)
    assert bool(cr) is True
    assert cr.arms["HCH"].n_refines == 3
    with pytest.raises(Exception):
        cr.hch_beats_hexpert = True            # frozen
    with pytest.raises(Exception):
        arm.name = "X"                          # frozen


from datetime import date

import pandas as pd

from youzi.loop.compare import compare_harnesses
from youzi.loop.inner_loop import LoopConfig
from youzi.harness.snapshot import SnapshotStore
from youzi.llm.client import MockLLMClient
from tests.conftest import FakeSource
from tests.test_inner_loop import _seed_h, _decision

_PICK_W = _decision("W")
_NO_TRADE = '{"candidates": [], "no_trade_reason": "空仓"}'


def _w_src():
    """单码 W 每日涨停(continued);3 日。"""
    days = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)]
    frames = {("zt", d): pd.DataFrame({"code": ["W"], "name": ["赢家"], "boards": [2]}) for d in days}
    return FakeSource(frames, days)


class _SeqFactory:
    """第 k 次调用返回第 k 个脚本对应的 client(超出则用最后一个);记 calls。"""
    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        c = MockLLMClient(self._scripts[min(self._i, len(self._scripts) - 1)])
        self._i += 1
        return c


class _CountFactory:
    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._fn()


def _compare(tmp_path, agent_scripts, refiner_script='{"ops": []}', cfg=None):
    src = _w_src()
    agent_f = _SeqFactory(agent_scripts)
    refiner_f = _SeqFactory([refiner_script])
    store_f = _CountFactory(lambda: SnapshotStore(tmp_path))
    harness_f = _CountFactory(_seed_h)
    rep = compare_harnesses(
        harness_f, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm_factory=agent_f, refiner_llm_factory=refiner_f,
        store_factory=store_f, loop_config=cfg or LoopConfig())
    return rep, agent_f, refiner_f, store_f, harness_f


def test_four_arms_and_verdict_true(tmp_path):
    # HCH 选 W(continued, mean=1.0);Hexpert 空仓(mean=0.0)→ HCH 胜
    rep, *_ = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert set(rep.arms) == {"HCH", "Hexpert", "Hmin_highest", "Hmin_notrade"}
    assert rep.arms["HCH"].report.mean_score == 1.0
    assert rep.arms["Hexpert"].report.mean_score == 0.0
    assert rep.arms["Hmin_highest"].report.mean_score == 1.0   # HighestBoard 也追 W
    assert rep.arms["Hmin_notrade"].report.mean_score == 0.0
    assert rep.hch_minus_hexpert_mean_score == 1.0
    assert rep.hch_beats_hexpert is True
    assert rep.arms["HCH"].n_refines >= 1                       # W 续板有证据 → refine 触发
    assert rep.arms["HCH"].n_breaker_trips == 0


def test_verdict_false_when_hch_worse(tmp_path):
    # HCH 空仓(mean=0.0);Hexpert 选 W(mean=1.0)→ HCH 退化于 frozen
    rep, *_ = _compare(tmp_path, [_NO_TRADE, _PICK_W])
    assert rep.hch_minus_hexpert_mean_score == -1.0
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines == 0                       # 全空仓无评分证据 → 不 refine


def test_same_script_delta_zero(tmp_path):
    # HCH 与 Hexpert 同脚本(都选 W)→ delta=0、verdict False,但 HCH 仍 refine(MockLLM 局限:refine 不改脚本化决策)
    rep, *_ = _compare(tmp_path, [_PICK_W])     # 两路都拿到 _PICK_W(SeqFactory 超出用末元素)
    assert rep.arms["HCH"].report.mean_score == rep.arms["Hexpert"].report.mean_score == 1.0
    assert rep.hch_minus_hexpert_mean_score == 0.0
    assert rep.hch_beats_hexpert is False
    assert rep.arms["HCH"].n_refines >= 1


def test_factory_call_counts_and_isolation(tmp_path):
    rep, agent_f, refiner_f, store_f, harness_f = _compare(tmp_path, [_PICK_W, _NO_TRADE])
    assert harness_f.calls == 2      # HCH + Hexpert 各一份 fresh H
    assert agent_f.calls == 2        # HCH agent + Hexpert agent
    assert refiner_f.calls == 1      # 仅 HCH refiner
    assert store_f.calls == 1        # 仅 HCH 用 store
