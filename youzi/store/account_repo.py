# youzi/store/account_repo.py
"""账户仓储:fill(唯一权威事实)+ account_snapshot(冻结副本 / 外部基线)。

**核心纪律:持仓与现金永远是"折叠 fills"的查询函数,不落第二份权威表。**
没有可被就地改写的 `position` 表 → 不存在"表与流水对不上"的经典账务腐烂。
`record_fill` 以 `operation_id` 幂等(UNIQUE 进 schema):同一笔操作重复提交
返回**已有**的 fill,不重复入账。

`account_snapshot` 的两种用法由 `source` 区分:
  · 基线(`BASELINE_SOURCES`,如 manual/broker/opening)= **外部真相**,给绝对现金
    一个起点(纯 fills 只能给出"净变动"),折叠时作为起算点,其后的 fill 叠加其上;
  · 其余(如 LiveDecisionService 写的 `frozen`)= 决策时刻的**冻结副本**,只作审计,
    **不参与**折叠基线的选取——否则派生值会反过来变成新的权威,破坏上面的纪律。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime as DateTime, date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.store.errors import NotFoundError

Side = Literal["buy", "sell"]

# 可作折叠起算点的快照来源(外部真相);其余来源(frozen 等)只作审计副本
BASELINE_SOURCES: frozenset[str] = frozenset({"manual", "broker", "opening"})

_FILL_COLS = ("fill_id", "operation_id", "account_id", "trade_date", "code", "side",
              "price", "qty", "fee", "decision_id", "created_at")


class Fill(BaseModel):
    """一笔已成交回报(frozen)。operation_id = 调用方给的幂等键。"""
    model_config = ConfigDict(frozen=True)
    fill_id: str
    operation_id: str
    account_id: str
    trade_date: Date
    code: str
    side: Side
    price: float = Field(gt=0)
    qty: int = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
    decision_id: str | None = None
    created_at: str

    def cash_delta(self) -> float:
        """现金变动:买 = −(price*qty + fee);卖 = +(price*qty − fee)。"""
        gross = self.price * self.qty
        return (gross - self.fee) if self.side == "sell" else -(gross + self.fee)


class Position(BaseModel):
    """折叠出的持仓(frozen)。avg_cost = 移动加权成本(含买入费)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    qty: int
    avg_cost: float
    cost_basis: float


class AccountView(BaseModel):
    """账户折叠视图(frozen)——**查询结果,不是存储**。

    `cash`:基线现金 + 其后 fills 的净现金变动。无基线时基线现金记 0.0,
    此时 `cash` 语义是**净变动**而非绝对现金,由 `baseline_as_of is None` 标明。
    `anomalies`:折叠过程中发现的账实不符(如超卖),**诚实登记不静默修正**。
    """
    model_config = ConfigDict(frozen=True)
    account_id: str
    as_of: str | None = None            # 折叠上界(None=至今)
    cash: float
    positions: list[Position] = Field(default_factory=list)
    realized_pnl: float = 0.0
    n_fills: int = 0                    # 叠加在基线之上的 fill 笔数
    baseline_as_of: str | None = None   # 基线快照时点;None = 无基线(cash 是净变动)
    baseline_source: str = ""
    anomalies: list[str] = Field(default_factory=list)

    @property
    def is_absolute_cash(self) -> bool:
        """cash 是否为绝对现金(有基线)而非净变动。"""
        return self.baseline_as_of is not None


class AccountSnapshotRow(BaseModel):
    """account_snapshot 一行(frozen)。"""
    model_config = ConfigDict(frozen=True)
    account_id: str
    as_of: str
    cash: float
    positions: dict[str, int] = Field(default_factory=dict)   # code -> qty
    source: str = ""
    created_at: str = ""


def _now() -> str:
    # 微秒精度:同秒内多笔成交的 since/until 过滤不至于互相吞掉
    return DateTime.now().isoformat(timespec="microseconds")


def _row_to_fill(row: sqlite3.Row) -> Fill:
    return Fill.model_validate({k: row[k] for k in _FILL_COLS})


class AccountRepo:
    """fill / account_snapshot 的纯仓储 + 折叠查询。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── fills ────────────────────────────────────────────────────────────
    def record_fill(self, *, operation_id: str, account_id: str, trade_date: Date,
                    code: str, side: Side, price: float, qty: int, fee: float = 0.0,
                    decision_id: str | None = None) -> tuple[Fill, bool]:
        """登记成交,**以 operation_id 幂等**。

        返回 `(fill, created)`:`created=False` 表示这条 operation_id 早已入账,
        返回的是**已有**记录,本次不重复入账(字段冲突亦不覆盖——先到为准,
        重复提交是网络重试的常态,静默改写才是事故)。
        """
        existing = self.fill_by_operation(operation_id)
        if existing is not None:
            return existing, False
        fid = uuid.uuid4().hex
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO fill (fill_id, operation_id, account_id, trade_date, code,"
                    " side, price, qty, fee, decision_id, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (fid, operation_id, account_id, trade_date.isoformat(), code, side,
                     float(price), int(qty), float(fee), decision_id, _now()))
        except sqlite3.IntegrityError:
            # 并发下同 operation_id 抢到 UNIQUE(Python 侧检查的 TOCTOU 兜底)
            dup = self.fill_by_operation(operation_id)
            if dup is not None:
                return dup, False
            raise
        return self.require_fill(fid), True

    def fill_by_operation(self, operation_id: str) -> Fill | None:
        row = self._conn.execute(
            "SELECT * FROM fill WHERE operation_id = ?", (operation_id,)).fetchone()
        return _row_to_fill(row) if row else None

    def require_fill(self, fill_id: str) -> Fill:
        row = self._conn.execute(
            "SELECT * FROM fill WHERE fill_id = ?", (fill_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"成交记录不存在: {fill_id}")
        return _row_to_fill(row)

    def fills(self, account_id: str, *, since: str | None = None,
              until: str | None = None) -> list[Fill]:
        """账户成交流水,**按入库顺序(rowid)升序**。

        排序键用 rowid 而非 created_at:同一秒内的多笔成交若按时间戳排,并列时
        会退化到随机的 fill_id,买卖顺序被打乱 → 成本结转算错。rowid 是单调
        入库序,与 created_at 同向且无并列(`_now()` 恒取当刻,不会倒流)。

        since/until 为 ISO 时间串:`since < created_at <= until`
        (since 排他 —— 基线时点当刻的持仓已计入基线,不可重复叠加)。
        """
        sql = "SELECT * FROM fill WHERE account_id = ?"
        args: list = [account_id]
        if since is not None:
            sql += " AND created_at > ?"
            args.append(since)
        if until is not None:
            sql += " AND created_at <= ?"
            args.append(until)
        sql += " ORDER BY rowid"
        return [_row_to_fill(r) for r in self._conn.execute(sql, args).fetchall()]

    # ── account_snapshot ─────────────────────────────────────────────────
    def put_snapshot(self, *, account_id: str, as_of: str, cash: float,
                     positions: dict[str, int], source: str = "") -> AccountSnapshotRow:
        """写(或按 (account_id, as_of) 覆盖)一份账户快照。"""
        with self._conn:
            self._conn.execute(
                "INSERT INTO account_snapshot (account_id, as_of, cash, positions_json,"
                " source, created_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(account_id, as_of) DO UPDATE SET"
                " cash=excluded.cash, positions_json=excluded.positions_json,"
                " source=excluded.source, created_at=excluded.created_at",
                (account_id, as_of, float(cash),
                 json.dumps(positions, ensure_ascii=False), source, _now()))
        snap = self.get_snapshot(account_id, as_of)
        assert snap is not None                       # 刚写入,必在
        return snap

    def get_snapshot(self, account_id: str, as_of: str) -> AccountSnapshotRow | None:
        row = self._conn.execute(
            "SELECT * FROM account_snapshot WHERE account_id = ? AND as_of = ?",
            (account_id, as_of)).fetchone()
        return _snapshot_row(row) if row else None

    def latest_baseline(self, account_id: str,
                        as_of: str | None = None) -> AccountSnapshotRow | None:
        """折叠起算点:`source ∈ BASELINE_SOURCES` 的最近一份快照(≤ as_of)。"""
        marks = ",".join("?" for _ in BASELINE_SOURCES)
        sql = (f"SELECT * FROM account_snapshot WHERE account_id = ?"
               f" AND source IN ({marks})")
        args: list = [account_id, *sorted(BASELINE_SOURCES)]
        if as_of is not None:
            sql += " AND as_of <= ?"
            args.append(as_of)
        sql += " ORDER BY as_of DESC LIMIT 1"
        row = self._conn.execute(sql, args).fetchone()
        return _snapshot_row(row) if row else None

    def snapshots(self, account_id: str) -> list[AccountSnapshotRow]:
        rows = self._conn.execute(
            "SELECT * FROM account_snapshot WHERE account_id = ? ORDER BY as_of",
            (account_id,)).fetchall()
        return [_snapshot_row(r) for r in rows]

    # ── 折叠(查询函数,非存储)───────────────────────────────────────────
    def fold(self, account_id: str, *, as_of: str | None = None) -> AccountView:
        """把 fills 折叠成持仓 + 现金。**唯一的持仓真相来源。**

        算法:移动加权平均成本。买 → qty+、cost_basis += 成交额+费;
        卖 → 按 avg_cost 结转成本、realized_pnl += 卖出净额 − 结转成本。
        超卖(卖出量 > 当前持仓)**照实施加**(qty 可为负)并登记 anomaly——
        钳零会把错账藏起来,负持仓是刺眼的、能被人看见并修正的。
        """
        base = self.latest_baseline(account_id, as_of)
        cash = base.cash if base else 0.0
        qty: dict[str, int] = dict(base.positions) if base else {}
        basis: dict[str, float] = {}
        if base:
            # 基线只给数量、不给成本 → 成本基准置 0,avg_cost 从 0 起算并登记说明
            basis = {c: 0.0 for c in qty}
        realized = 0.0
        anomalies: list[str] = []
        if base and any(v for v in qty.values()):
            anomalies.append(
                f"基线快照({base.as_of}, source={base.source})只含持仓数量、无成本价,"
                "其 avg_cost 以 0 计,勿据此算浮盈")

        rows = self.fills(account_id, since=(base.as_of if base else None), until=as_of)
        for f in rows:
            cash += f.cash_delta()
            held = qty.get(f.code, 0)
            if f.side == "buy":
                qty[f.code] = held + f.qty
                basis[f.code] = basis.get(f.code, 0.0) + f.price * f.qty + f.fee
            else:
                if f.qty > held:
                    anomalies.append(
                        f"超卖 {f.code}:卖 {f.qty} > 持 {held}(fill {f.fill_id});"
                        "持仓已按实记为负,请核对流水或补录基线快照")
                avg = (basis.get(f.code, 0.0) / held) if held > 0 else 0.0
                out_cost = avg * f.qty
                realized += (f.price * f.qty - f.fee) - out_cost
                qty[f.code] = held - f.qty
                basis[f.code] = basis.get(f.code, 0.0) - out_cost

        positions = [
            Position(code=c, qty=q, cost_basis=round(basis.get(c, 0.0), 6),
                     avg_cost=round(basis.get(c, 0.0) / q, 6) if q > 0 else 0.0)
            for c, q in sorted(qty.items()) if q != 0            # 清仓的不再列出
        ]
        return AccountView(
            account_id=account_id, as_of=as_of, cash=round(cash, 6),
            positions=positions, realized_pnl=round(realized, 6), n_fills=len(rows),
            baseline_as_of=(base.as_of if base else None),
            baseline_source=(base.source if base else ""), anomalies=anomalies)

    def positions(self, account_id: str, *, as_of: str | None = None) -> list[Position]:
        """折叠出的持仓列表(fold 的便捷投影)。"""
        return self.fold(account_id, as_of=as_of).positions


def _snapshot_row(row: sqlite3.Row) -> AccountSnapshotRow:
    try:
        pos = json.loads(row["positions_json"])
    except json.JSONDecodeError:
        pos = {}
    if not isinstance(pos, dict):
        pos = {}
    return AccountSnapshotRow(
        account_id=row["account_id"], as_of=row["as_of"], cash=row["cash"],
        positions={str(k): int(v) for k, v in pos.items()},
        source=row["source"] or "", created_at=row["created_at"] or "")
