# tests/test_account_repo.py
"""AccountRepo:record_fill 幂等 + positions/cash = fold(fills)。"""
from datetime import date

import pytest

from youzi.store.account_repo import AccountRepo
from youzi.store.db import connect

D = date(2024, 6, 26)


@pytest.fixture
def repo():
    return AccountRepo(connect(":memory:"))


def _buy(repo, op, code="600000", price=10.0, qty=100, fee=0.0, account="A"):
    return repo.record_fill(operation_id=op, account_id=account, trade_date=D,
                            code=code, side="buy", price=price, qty=qty, fee=fee)


def _sell(repo, op, code="600000", price=12.0, qty=100, fee=0.0, account="A"):
    return repo.record_fill(operation_id=op, account_id=account, trade_date=D,
                            code=code, side="sell", price=price, qty=qty, fee=fee)


# ── 幂等 ─────────────────────────────────────────────────────────────────
def test_record_fill_is_idempotent_on_operation_id(repo):
    first, created = _buy(repo, "op1", price=10.0)
    assert created is True
    again, created2 = _buy(repo, "op1", price=999.0, qty=9999)   # 同 op、不同内容
    assert created2 is False
    assert again.fill_id == first.fill_id
    assert (again.price, again.qty) == (10.0, 100)   # 先到为准,不被重复提交改写
    assert len(repo.fills("A")) == 1                  # 只入账一次


def test_idempotency_does_not_double_count_in_fold(repo):
    _buy(repo, "op1", qty=100)
    for _ in range(5):
        _buy(repo, "op1", qty=100)                    # 网络重试 5 次
    view = repo.fold("A")
    assert view.n_fills == 1
    assert [(p.code, p.qty) for p in view.positions] == [("600000", 100)]


def test_distinct_operation_ids_both_land(repo):
    _buy(repo, "op1", qty=100)
    _buy(repo, "op2", qty=200)
    assert repo.fold("A").positions[0].qty == 300


# ── 折叠正确性 ───────────────────────────────────────────────────────────
def test_fold_computes_qty_avg_cost_and_cash(repo):
    _buy(repo, "b1", price=10.0, qty=100, fee=5.0)     # 成本 1005
    _buy(repo, "b2", price=12.0, qty=100, fee=5.0)     # 成本 1205 → 合计 2210 / 200
    view = repo.fold("A")
    pos = view.positions[0]
    assert pos.qty == 200
    assert pos.cost_basis == pytest.approx(2210.0)
    assert pos.avg_cost == pytest.approx(11.05)
    assert view.cash == pytest.approx(-2210.0)         # 无基线 → cash 是净变动
    assert view.is_absolute_cash is False


def test_fold_sell_realizes_pnl_and_reduces_position(repo):
    _buy(repo, "b1", price=10.0, qty=200, fee=0.0)     # avg 10
    _sell(repo, "s1", price=12.0, qty=100, fee=1.0)    # 卖净 1199,结转成本 1000
    view = repo.fold("A")
    assert view.positions[0].qty == 100
    assert view.positions[0].cost_basis == pytest.approx(1000.0)
    assert view.realized_pnl == pytest.approx(199.0)
    assert view.cash == pytest.approx(-2000.0 + 1199.0)


def test_fold_drops_flat_positions(repo):
    _buy(repo, "b1", qty=100)
    _sell(repo, "s1", qty=100)
    assert repo.fold("A").positions == []              # 清仓的不再列出
    assert repo.positions("A") == []


def test_fold_is_account_scoped(repo):
    _buy(repo, "b1", qty=100, account="A")
    _buy(repo, "b2", qty=300, account="B")
    assert repo.fold("A").positions[0].qty == 100
    assert repo.fold("B").positions[0].qty == 300


def test_fold_records_oversell_anomaly_without_silent_clamp(repo):
    """超卖照实记为负持仓 + 登记 anomaly——钳零会把错账藏起来。"""
    _buy(repo, "b1", qty=100)
    _sell(repo, "s1", qty=300)
    view = repo.fold("A")
    assert view.positions[0].qty == -200
    assert any("超卖" in a for a in view.anomalies)


def test_fold_as_of_upper_bound(repo):
    f1, _ = _buy(repo, "b1", qty=100)
    _buy(repo, "b2", qty=100)
    # 截到第一笔的登记时刻(闭区间上界)→ 只折叠第一笔
    view = repo.fold("A", as_of=f1.created_at)
    assert view.n_fills == 1 and view.positions[0].qty == 100
    assert repo.fold("A").positions[0].qty == 200      # 不截则两笔都算


def test_fold_order_is_insertion_order_not_timestamp_ties(repo):
    """同秒内买后卖:必须按入库序结转成本,不能被时间戳并列打乱。"""
    for i in range(6):
        _buy(repo, f"b{i}", price=10.0, qty=100)
        _sell(repo, f"s{i}", price=11.0, qty=100)
    view = repo.fold("A")
    assert view.positions == []                         # 每轮买 100 卖 100 → 清仓
    assert view.realized_pnl == pytest.approx(6 * 100.0)
    assert view.anomalies == []                         # 顺序对,就不该有超卖告警


# ── 快照 / 基线 ──────────────────────────────────────────────────────────
def test_baseline_snapshot_gives_absolute_cash(repo):
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=100000.0,
                      positions={}, source="manual")
    _buy(repo, "b1", price=10.0, qty=100, fee=5.0)
    view = repo.fold("A")
    assert view.is_absolute_cash is True
    assert view.baseline_source == "manual"
    assert view.cash == pytest.approx(100000.0 - 1005.0)


def test_frozen_snapshot_is_not_a_fold_baseline(repo):
    """决策时刻的冻结副本(source='frozen')只作审计,绝不反过来当权威基线。"""
    _buy(repo, "b1", price=10.0, qty=100)
    repo.put_snapshot(account_id="A", as_of="2024-06-26T15:00:00", cash=-1000.0,
                      positions={"600000": 100}, source="frozen")
    view = repo.fold("A")
    assert view.baseline_as_of is None                 # frozen 不入选基线
    assert view.is_absolute_cash is False
    assert view.positions[0].qty == 100                # 仍是 fills 折叠出来的,没被翻倍


def test_snapshot_upsert_and_listing(repo):
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=1.0,
                      positions={"600000": 100}, source="manual")
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=2.0,
                      positions={}, source="manual")   # 同 (account, as_of) → 覆盖
    snaps = repo.snapshots("A")
    assert len(snaps) == 1 and snaps[0].cash == 2.0 and snaps[0].positions == {}


def test_latest_baseline_picks_most_recent_before_as_of(repo):
    repo.put_snapshot(account_id="A", as_of="2024-06-20T15:00:00", cash=1.0,
                      positions={}, source="manual")
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=2.0,
                      positions={}, source="broker")
    assert repo.latest_baseline("A").cash == 2.0
    assert repo.latest_baseline("A", as_of="2024-06-24T00:00:00").cash == 1.0
    assert repo.latest_baseline("A", as_of="2024-06-01T00:00:00") is None


def test_baseline_positions_warn_about_missing_cost(repo):
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=5000.0,
                      positions={"600000": 500}, source="broker")
    view = repo.fold("A")
    assert view.positions[0].qty == 500
    assert any("无成本价" in a for a in view.anomalies)   # 诚实提示,不臆造成本
