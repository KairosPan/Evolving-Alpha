# tests/test_return_scorer_c3.py
"""C3 可成交收益尺:T+1 守门 + 一字板成交 + 成本 + unfillable/missing 一等公民 + 路径 stop-on-nuke。"""
from datetime import date

import pandas as pd
import pytest

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.fill import CostModel
from youzi.eval.oracle import DayMembership
from youzi.eval.scorer import ReturnScorer
from tests.conftest import FakeSource

D1, D2, D3, D4 = date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4)
CAL = [D1, D2, D3, D4]
COST = CostModel().round_trip_cost()   # 0.0041


def _decision(*cands, d=D1):
    cs = [Candidate(code=c[0], name=c[1], pattern="p") if isinstance(c, tuple)
          else Candidate(code=c, name="", pattern="p") for c in cands]
    return DecisionPackage(date=d, candidates=cs)


def _ohlcv(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def _mem(limit_up=(), blowup=(), limit_down=()):
    return DayMembership(limit_up=frozenset(limit_up), blowup=frozenset(blowup),
                         limit_down=frozenset(limit_down))


def test_requires_horizon_ge_2_raises_on_same_day():
    # T+1 守门下沉到 scorer:entry_day==exit_day(horizon=1 同日买卖)直接 raise
    src = FakeSource({}, CAL)
    with pytest.raises(ValueError):
        ReturnScorer().score_step(_decision("600000"), [_mem(limit_up={"600000"})],
                                  D2, D2, src)


def test_normal_fill_net_return_with_cost():
    # t(6/1)close=10;entry(6/2)open=10.3 普通成交;exit(6/3)close=11;全程封板→continued
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.3, 10.6, 10.1, 10.5, 1),
                 (D3, 10.8, 11.2, 10.7, 11.0, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    mems = [_mem(limit_up={"600000"}), _mem(limit_up={"600000"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某股")), mems, D2, D3, src)["600000"]
    assert sc.outcome == "continued"
    assert sc.settle == "normal"
    assert sc.score == pytest.approx((11.0 - 10.3) / 10.3 - COST)


def test_one_word_board_is_unfillable():
    # entry 一字板(open=high=low=11=+10% 主板)→ 买不进
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 11.0, 11.0, 11.0, 11.0, 1),
                 (D3, 11.5, 12, 11, 11.8, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    mems = [_mem(limit_up={"600000"}), _mem(limit_up={"600000"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某股")), mems, D2, D3, src)["600000"]
    assert sc.outcome == "unfillable"
    assert sc.score == 0.0


def test_missing_ohlcv_is_missing_not_dropped():
    src = FakeSource({}, CAL, ohlcv={})                 # 无任何 OHLCV
    mems = [_mem(limit_up={"600000"}), _mem(limit_up={"600000"})]
    out = ReturnScorer().score_step(_decision(("600000", "某")), mems, D2, D3, src)
    assert "600000" in out                              # 绝不静默丢弃
    assert out["600000"].outcome == "missing"
    assert out["600000"].score == 0.0


def test_stop_on_nuke_settles_at_nuke_day_not_rebound():
    # horizon=3:entry 6/2 普通@10.3;6/3 跌停(nuke,index1)→ stop@6/3 close=9;6/4 反弹 12 不计
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.3, 10.6, 10.1, 10.5, 1),
                 (D3, 9.2, 9.5, 9.0, 9.0, 1), (D4, 11, 12, 11, 12.0, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    mems = [_mem(limit_up={"600000"}), _mem(limit_down={"600000"}), _mem(limit_up={"600000"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某")), mems, D2, D4, src)["600000"]
    assert sc.outcome == "nuked"
    assert sc.settle == "stop_on_nuke"
    assert sc.score == pytest.approx((9.0 - 10.3) / 10.3 - COST)   # 用 6/3 close,非 6/4


def test_stop_on_nuke_on_entry_day_settles_next_day_t_plus_1():
    # entry 6/2 即跌停(index0):T+1 不能当日卖 → 顺延 6/3 close 结算(首个可卖日)
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 9.5, 9.8, 9.0, 9.0, 1),
                 (D3, 8.5, 9, 8.4, 8.5, 1), (D4, 9, 9, 9, 9.0, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    mems = [_mem(limit_down={"600000"}), _mem(limit_down={"600000"}), _mem(limit_up={"600000"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某")), mems, D2, D4, src)["600000"]
    assert sc.outcome == "nuked"
    assert sc.score == pytest.approx((8.5 - 9.5) / 9.5 - COST)      # fill@9.5 → settle 6/3 close=8.5


def test_advantage_vs_pool_net_return_baseline():
    # 决策日池 {600000, 600001} 均普通成交@开盘=10;baseline=两者净收益均值;advantage=候选净−baseline
    df0 = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.0, 10.2, 9.9, 10.5, 1),
                  (D3, 10.8, 11.2, 10.7, 11.0, 1)])     # net = (11-10)/10 - COST = 0.1 - COST
    df1 = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.0, 10.2, 9.9, 10.2, 1),
                  (D3, 10.3, 10.6, 10.2, 10.5, 1)])     # net = (10.5-10)/10 - COST = 0.05 - COST
    src = FakeSource({}, CAL, ohlcv={"600000": df0, "600001": df1})
    dm = _mem(limit_up={"600000", "600001"})
    mems = [_mem(limit_up={"600000", "600001"}), _mem(limit_up={"600000", "600001"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某")), mems, D2, D3, src,
                                   decision_mem=dm)["600000"]
    net0, net1 = 0.1 - COST, 0.05 - COST
    base = (net0 + net1) / 2
    assert sc.day_baseline == pytest.approx(base)
    assert sc.advantage == pytest.approx(net0 - base)              # cost 抵消 → ≈ 0.025


def test_baseline_none_when_pool_has_no_fillable_returns():
    # 决策日池只含缺数成员(600001 无 OHLCV)→ 基线 None;候选 600000 有净收益 → advantage 回退=score
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.0, 10.2, 9.9, 10.5, 1),
                 (D3, 10.8, 11.2, 10.7, 11.0, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    dm = _mem(limit_up={"600001"})                     # 池里只有缺 OHLCV 的 600001
    mems = [_mem(limit_up={"600000"}), _mem(limit_up={"600000"})]
    sc = ReturnScorer().score_step(_decision(("600000", "某")), mems, D2, D3, src,
                                   decision_mem=dm)["600000"]
    assert sc.day_baseline is None
    assert sc.advantage == sc.score


def test_name_fallback_from_entry_pool_for_main_board_st(tmp_path=None):
    # revision 6:候选 name 为空 → 回退入场日 zt_pool 行的 name。
    # 主板 ST(600519,zt 池名含 ST)+5% 一字板:有回退→5% 阈值→unfillable;无回退→10%→普通成交。
    code = "600519"
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.5, 10.5, 10.5, 10.5, 1),
                 (D3, 10.8, 11, 10.7, 10.9, 1)])
    frames = {("zt", D2): pd.DataFrame({"code": [code], "name": ["ST某"], "boards": [1]})}
    src = FakeSource(frames, CAL, ohlcv={code: df})
    mems = [_mem(limit_up={code}), _mem(limit_up={code})]
    sc = ReturnScorer().score_step(_decision(code), mems, D2, D3, src)[code]   # 候选 name=""
    assert sc.outcome == "unfillable"          # 回退取到 ST 名 → 5% 阈值 → +5% 一字板买不进


def test_cost_model_zero_gives_gross_return():
    df = _ohlcv([(D1, 10, 10, 10, 10.0, 1), (D2, 10.0, 10.2, 9.9, 10.5, 1),
                 (D3, 10.8, 11.2, 10.7, 11.0, 1)])
    src = FakeSource({}, CAL, ohlcv={"600000": df})
    mems = [_mem(limit_up={"600000"}), _mem(limit_up={"600000"})]
    scorer = ReturnScorer(CostModel(commission_bp=0, stamp_tax_bp=0, slippage_bp=0))
    sc = scorer.score_step(_decision(("600000", "某")), mems, D2, D3, src)["600000"]
    assert sc.score == pytest.approx((11.0 - 10.0) / 10.0)         # 毛收益 0.10
