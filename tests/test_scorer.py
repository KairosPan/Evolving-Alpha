# tests/test_scorer.py
from datetime import date

from youzi.eval.scorer import PoolScorer
from youzi.eval.oracle import DayMembership
from youzi.eval.decision import DecisionPackage, Candidate

# ReturnScorer 的 C3 收益尺行为(T+1/fill/成本/unfillable/missing/路径)见 test_return_scorer_c3.py。


def _decision(*codes):
    return DecisionPackage(date=date(2026, 6, 1),
                           candidates=[Candidate(code=c, name=c, pattern="p") for c in codes])


def test_pool_scorer_matches_pool_membership():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B", "A"), [mem],
                                  date(2026, 6, 2), date(2026, 6, 2), None)
    assert set(out) == {"A", "B"}                       # 去重
    assert out["A"].outcome == "continued" and out["A"].score == 1.0
    assert out["B"].outcome == "nuked" and out["B"].score == -1.0


# ── C2:day_baseline / advantage ──────────────────────────────────────────────

def test_pool_scorer_day_baseline_and_advantage_hand_computed():
    # 决策日池 {A, C};exit 日:A continued(+1)、C 掉出全部池 → faded(0)
    # → day_baseline = (1+0)/2 = 0.5(闭眼买全池的同日期望)
    decision_mem = DayMembership(limit_up=frozenset({"A", "C"}), blowup=frozenset(),
                                 limit_down=frozenset())
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B"), [mem],
                                  date(2026, 6, 2), date(2026, 6, 2), None,
                                  decision_mem=decision_mem)
    assert out["A"].day_baseline == 0.5
    assert out["A"].advantage == 0.5                     # 1.0 − 0.5
    assert out["B"].advantage == -1.5                    # nuked:−1.0 − 0.5
    assert out["A"].score == 1.0                         # 原始分不动


def test_pool_scorer_empty_pool_baseline_none_advantage_falls_back():
    # 空池日约定:决策日 limit_up 空(或 decision_mem=None)→ baseline=None,advantage 回退=score
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(), limit_down=frozenset())
    empty = DayMembership(limit_up=frozenset(), blowup=frozenset(), limit_down=frozenset())
    for dm in (empty, None):
        out = PoolScorer().score_step(_decision("A"), [mem],
                                      date(2026, 6, 2), date(2026, 6, 2), None,
                                      decision_mem=dm)
        assert out["A"].day_baseline is None
        assert out["A"].advantage == out["A"].score == 1.0


# ── C3 slice 3:协议 mem → mems(持有路径逐日成员);PoolScorer 取 mems[-1] ──────

def test_pool_scorer_uses_exit_day_from_mems_path():
    # 新协议:mems=entry..exit 逐日成员;PoolScorer 用 mems[-1](exit 日)保持终点语义。
    # 入场日 A 封板,exit 日 A 跌停 → 终点判 nuked(证 mems[-1] 被采用,非 mems[0])。
    entry_mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(), limit_down=frozenset())
    exit_mem = DayMembership(limit_up=frozenset(), blowup=frozenset(), limit_down=frozenset({"A"}))
    out = PoolScorer().score_step(_decision("A"), [entry_mem, exit_mem],
                                  date(2026, 6, 2), date(2026, 6, 3), None)
    assert out["A"].outcome == "nuked"
    assert out["A"].score == -1.0
