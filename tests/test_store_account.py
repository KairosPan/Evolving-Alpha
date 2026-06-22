import pytest

from youzi.store.account import EMPTY_POSITION, apply_buy, apply_sell


def test_buy_sets_avg_cost_including_fee():
    s = apply_buy(EMPTY_POSITION, price=10.0, qty=100, fee=5.0)
    assert s.qty_open == 100
    assert s.avg_cost == pytest.approx((10.0 * 100 + 5.0) / 100)   # 10.05
    assert s.status == "open"


def test_batched_buys_weighted_average():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)          # fee 缺省 None → 0
    s = apply_buy(s, 12.0, 100)
    assert s.qty_open == 200
    assert s.avg_cost == pytest.approx(11.0)


def test_sell_realizes_pnl_and_closes_on_zero():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    s = apply_sell(s, price=12.0, qty=100, fee=3.0)
    assert s.qty_open == 0
    assert s.realized_pnl == pytest.approx((12.0 - 10.0) * 100 - 3.0)  # 197.0
    assert s.status == "closed"


def test_partial_sell_keeps_open():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    s = apply_sell(s, 11.0, 40)
    assert s.qty_open == 60
    assert s.status == "open"
    assert s.realized_pnl == pytest.approx((11.0 - 10.0) * 40)


def test_oversell_raises():
    s = apply_buy(EMPTY_POSITION, 10.0, 100)
    with pytest.raises(ValueError):
        apply_sell(s, 11.0, 101)
