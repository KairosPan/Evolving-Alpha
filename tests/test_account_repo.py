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
    again, created2 = _buy(repo, "op1", price=10.0)   # 同 op、同内容 = 网络重试
    assert created2 is False
    assert again.fill_id == first.fill_id
    assert len(repo.fills("A")) == 1                  # 只入账一次
    # 同 op、不同内容 ≠ 重试 → 大声拒绝(见 test_record_fill_same_op_different_fields)


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


# ── 时间参数纪律 ─────────────────────────────────────────────────────────
def test_date_only_time_params_are_rejected(repo):
    """日期粒度的时间参数会静默排除/重放当日成交 → 一律大声拒绝(不猜语义)。"""
    _buy(repo, "b1")
    with pytest.raises(ValueError):
        repo.fold("A", as_of="2024-06-26")
    with pytest.raises(ValueError):
        repo.fills("A", since="2024-06-26")
    with pytest.raises(ValueError):
        repo.fills("A", until="not-a-date")
    with pytest.raises(ValueError):
        repo.put_snapshot(account_id="A", as_of="2024-06-26", cash=1.0,
                          positions={}, source="manual")


def test_backfill_after_baseline_is_flagged(repo):
    """基线之后补录更早交易日的成交 → 重复计账嫌疑,登记 anomaly 不静默。"""
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=100000.0,
                      positions={}, source="broker")
    repo.record_fill(operation_id="old1", account_id="A", trade_date=date(2024, 6, 20),
                     code="600000", side="buy", price=10.0, qty=100)
    view = repo.fold("A")
    assert any("补录" in a for a in view.anomalies)
    _buy(repo, "new1")                        # trade_date=6/26 ≥ 基线日 → 不该误报
    view2 = repo.fold("A")
    assert sum("补录" in a for a in view2.anomalies) == 1


# ── 开户(opening 基线)─────────────────────────────────────────────────
def test_open_baseline_gives_absolute_cash(repo):
    snap = repo.open_baseline(account_id="A", cash=200_000.0)
    assert snap.source == "opening" and snap.positions == {}
    view = repo.fold("A")
    assert view.is_absolute_cash is True and view.cash == pytest.approx(200_000.0)


def test_open_baseline_twice_is_rejected(repo):
    from youzi.store.errors import DuplicateError
    repo.open_baseline(account_id="A", cash=1000.0)
    with pytest.raises(DuplicateError):
        repo.open_baseline(account_id="A", cash=2000.0)
    repo.open_baseline(account_id="B", cash=1.0)     # 其他账户不受影响


def test_open_baseline_nonpositive_cash_is_rejected(repo):
    with pytest.raises(ValueError):
        repo.open_baseline(account_id="A", cash=0.0)


def test_opening_baseline_backfill_is_not_flagged(repo):
    """opening 基线=空仓起点,补录历史交易日成交是模拟盘常规操作,不告警。"""
    repo.open_baseline(account_id="A", cash=100_000.0)
    repo.record_fill(operation_id="old1", account_id="A", trade_date=date(2024, 6, 20),
                     code="600000", side="buy", price=10.0, qty=100)
    assert not any("补录" in a for a in repo.fold("A").anomalies)


def test_record_fill_same_op_different_fields_is_rejected(repo):
    """幂等键被复用提交另一笔不同成交 → 大声拒绝,不静默返回旧记录当假确认。"""
    from youzi.store.errors import DuplicateError
    _buy(repo, "op1", price=10.0, qty=100)
    with pytest.raises(DuplicateError):
        _buy(repo, "op1", price=11.0, qty=100)       # 同键不同价
    with pytest.raises(DuplicateError):
        _sell(repo, "op1", price=10.0, qty=100)      # 同键不同方向
    with pytest.raises(DuplicateError):
        _buy(repo, "op1", price=10.0, qty=100, account="B")   # 跨账户碰撞
    same, created = _buy(repo, "op1", price=10.0, qty=100)    # 字段一致 = 合法重试
    assert created is False and same.operation_id == "op1"


def test_open_baseline_with_existing_fills_is_rejected(repo):
    """已有流水再开 opening 基线会把既有成交从折叠里静默剔除 → 拒绝。"""
    from youzi.store.errors import DuplicateError
    _buy(repo, "b1")
    with pytest.raises(DuplicateError):
        repo.open_baseline(account_id="A", cash=100_000.0)
    repo.open_baseline(account_id="B", cash=1.0)     # 无流水的账户不受影响


def test_fold_exposes_baseline_codes(repo):
    """基线来源持仓(无成本价)的 code 集合暴露给上层,浮盈展示可据此留空。"""
    repo.put_snapshot(account_id="A", as_of="2024-06-25T15:00:00", cash=5000.0,
                      positions={"600000": 500, "600001": 0}, source="broker")
    view = repo.fold("A")
    assert view.baseline_codes == ["600000"]         # qty=0 的不算
    assert repo.fold("Z").baseline_codes == []
