# tests/test_scorer.py
from datetime import date

import pandas as pd

from youzi.eval.scorer import PoolScorer, ReturnScorer
from youzi.eval.oracle import DayMembership
from youzi.eval.decision import DecisionPackage, Candidate
from tests.conftest import FakeSource


def _decision(*codes):
    return DecisionPackage(date=date(2026, 6, 1),
                           candidates=[Candidate(code=c, name=c, pattern="p") for c in codes])


def _ohlcv(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_pool_scorer_matches_pool_membership():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B", "A"), mem,
                                  date(2026, 6, 2), date(2026, 6, 2), None)
    assert set(out) == {"A", "B"}                       # 去重
    assert out["A"].outcome == "continued" and out["A"].score == 1.0
    assert out["B"].outcome == "nuked" and out["B"].score == -1.0


def test_return_scorer_uses_return_and_drops_missing():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset())
    # A 有 OHLCV:entry open@6/2=10 → exit close@6/3=12 → +0.20;B 无 OHLCV → 丢弃
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10, 12.0, 200)])
    src = FakeSource({}, [], ohlcv={"A": df})
    out = ReturnScorer().score_step(_decision("A", "B"), mem,
                                    date(2026, 6, 2), date(2026, 6, 3), src)
    assert set(out) == {"A"}                             # B 缺收益被丢弃
    assert out["A"].outcome == "continued"               # outcome 仍池类别
    assert out["A"].score == 0.20                        # score = 收益
