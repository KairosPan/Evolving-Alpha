# tests/test_metrics_fill.py
"""C3 slice 5:EvalReport 把 unfillable/missing 排除出 mean/n_candidates,
报 fill_rate / n_unfillable / n_missing + all_in 双口径(unfillable 计 0)。"""
from datetime import date

import pytest

from youzi.eval.metrics import EvalReport, ScoredCandidate, build_report


def _sc(outcome, score, code="X", pattern="p", advantage=None):
    return ScoredCandidate(decision_date=date(2026, 6, 1), code=code, pattern=pattern,
                           outcome=outcome, score=score,
                           advantage=advantage if advantage is not None else score)


def test_nontrades_excluded_from_mean_and_counted_separately():
    items = [_sc("continued", 0.10, "A"), _sc("faded", 0.0, "B"), _sc("nuked", -0.20, "C"),
             _sc("unfillable", 0.0, "D"), _sc("missing", 0.0, "E")]
    rep = build_report(items, n_decisions=3, n_no_trade=0, horizon=2)
    assert rep.n_candidates == 3                         # 仅真实成交(continued/faded/nuked)
    assert rep.n_unfillable == 1
    assert rep.n_missing == 1
    assert rep.hit_rate == pytest.approx(1 / 3)          # continued / 真实成交数
    assert rep.nuke_rate == pytest.approx(1 / 3)
    assert rep.mean_score == pytest.approx((0.10 + 0.0 - 0.20) / 3)   # filled 口径
    assert rep.fill_rate == pytest.approx(3 / 4)         # filled / (filled + unfillable)
    assert rep.mean_score_all_in == pytest.approx((0.10 + 0.0 - 0.20 + 0.0) / 4)  # unfillable 计 0


def test_pool_only_report_backward_compatible():
    # 池制(无 unfillable/missing)→ 新字段恒等中性,旧断言不变
    items = [_sc("continued", 1.0, "A"), _sc("nuked", -1.0, "B")]
    rep = build_report(items, 2, 0, horizon=1)
    assert rep.n_candidates == 2
    assert rep.n_unfillable == 0 and rep.n_missing == 0
    assert rep.fill_rate == 1.0
    assert rep.hit_rate == 0.5
    assert rep.mean_score == pytest.approx(0.0)
    assert rep.mean_score_all_in == pytest.approx(rep.mean_score)   # 无 unfillable → 两口径相等


def test_all_missing_gives_zero_and_fill_rate_one():
    items = [_sc("missing", 0.0, "A"), _sc("missing", 0.0, "B")]
    rep = build_report(items, 2, 0, horizon=2)
    assert rep.n_candidates == 0 and rep.n_missing == 2
    assert rep.mean_score == 0.0 and rep.mean_score_all_in == 0.0
    assert rep.fill_rate == 1.0                          # 无成交尝试 → 约定 1.0


def test_by_pattern_only_counts_real_trades():
    items = [_sc("continued", 0.1, "A", pattern="relay"), _sc("unfillable", 0.0, "B", pattern="relay")]
    rep = build_report(items, 1, 0, horizon=2)
    assert rep.by_pattern["relay"].n == 1                # unfillable 不进 by_pattern


def test_old_json_backfills_all_in_from_mean_score():
    # 旧 run-store JSON 无 mean_score_all_in 字段 → 反序列化回填=mean_score(池制不变量,不破历史)
    rep = EvalReport(n_decisions=2, n_no_trade=0, n_candidates=2,
                     hit_rate=0.5, nuke_rate=0.0, mean_score=0.33)   # 不传 mean_score_all_in
    assert rep.mean_score_all_in == pytest.approx(0.33)
