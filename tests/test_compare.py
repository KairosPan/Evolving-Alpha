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
