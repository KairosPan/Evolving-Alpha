from datetime import date
from youzi.eval.metrics import ScoredCandidate, EvalReport, build_report


def _sc(code, pattern, oc, score):
    return ScoredCandidate(decision_date=date(2024, 6, 27), code=code,
                           pattern=pattern, outcome=oc, score=score)


def test_build_report_aggregates():
    scored = [
        _sc("A", "highest_board", "continued", 1.0),
        _sc("B", "highest_board", "nuked", -1.0),
        _sc("C", "w2s", "continued", 1.0),
        _sc("D", "w2s", "faded", 0.0),
    ]
    rep = build_report(scored, n_decisions=4, n_no_trade=1)
    assert rep.n_candidates == 4 and rep.n_decisions == 4 and rep.n_no_trade == 1
    assert rep.horizon == 1               # 默认
    assert rep.hit_rate == 0.5            # 2 continued / 4
    assert rep.nuke_rate == 0.25          # 1 nuked / 4
    assert abs(rep.mean_score - (1 - 1 + 1 + 0) / 4) < 1e-9   # 0.25
    hb = rep.by_pattern["highest_board"]
    assert hb.n == 2 and hb.hit_rate == 0.5 and hb.mean_score == 0.0
    assert hb.nuke_rate == 0.5                # highest_board: 1 nuked of 2
    w2s = rep.by_pattern["w2s"]
    assert w2s.n == 2 and w2s.hit_rate == 0.5 and w2s.mean_score == 0.5
    assert w2s.nuke_rate == 0.0


def test_build_report_empty():
    rep = build_report([], n_decisions=3, n_no_trade=3)
    assert rep.n_candidates == 0 and rep.hit_rate == 0.0 and rep.mean_score == 0.0
    assert rep.by_pattern == {}


def test_build_report_horizon_passthrough():
    rep = build_report([], n_decisions=3, n_no_trade=3, horizon=2)
    assert rep.horizon == 2


def test_build_report_all_nuked():
    scored = [_sc("A", "p", "nuked", -1.0), _sc("B", "p", "nuked", -1.0)]
    rep = build_report(scored, n_decisions=2, n_no_trade=0)
    assert rep.hit_rate == 0.0 and rep.nuke_rate == 1.0 and rep.mean_score == -1.0
