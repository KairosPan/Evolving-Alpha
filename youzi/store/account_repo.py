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

from youzi.store.errors import DuplicateError, NotFoundError

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
    baseline_codes: list[str] = Field(default_factory=list)   # 数量含基线来源的 code(无成本价,浮盈不可算)
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


def ensure_full_ts(value: str, param: str) -> str:
    """时间参数必须是**含时间部分**的完整 ISO 串,否则大声拒绝。

    fills 的时间过滤靠字符串字典序与微秒级 `created_at` 比较:只给日期
    ("2026-08-27")时,当日一切 "2026-08-27T…" 都比它**大**——作 until 会把
    当日成交静默排除,作基线 as_of 会把已计入基线的当日成交重放叠加。
    这类参数错是错账源头,不能靠约定,必须在入口拒绝。
    """
    try:
        DateTime.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{param} 不是合法 ISO 时间串: {value!r}") from e
    if "T" not in value:
        raise ValueError(
            f"{param} 需为含时间部分的完整 ISO datetime(如 2026-08-27T15:00:00),"
            f"收到日期粒度 {value!r}——字典序过滤会静默排除/重放当日成交")
    return value


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
        且**本次提交与已有记录字段一致**(网络重试的常态),不重复入账。
        同 operation_id 携带**不同**字段 → `DuplicateError`:那不是重试,是幂等键
        被复用提交另一笔交易,静默返回旧记录会把新成交丢掉还给出假确认。
        """

        def _settle(existing: Fill) -> tuple[Fill, bool]:
            same = (existing.account_id == account_id
                    and existing.trade_date == trade_date
                    and existing.code == code and existing.side == side
                    and existing.price == float(price) and existing.qty == int(qty)
                    and existing.fee == float(fee)
                    and existing.decision_id == decision_id)
            if not same:
                raise DuplicateError(
                    f"operation_id {operation_id!r} 已被另一笔不同成交占用"
                    f"(已有:{existing.account_id} {existing.trade_date} {existing.code}"
                    f" {existing.side} {existing.price}×{existing.qty});"
                    "请换新的 operation_id 提交本笔")
            return existing, False

        existing = self.fill_by_operation(operation_id)
        if existing is not None:
            return _settle(existing)
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
                return _settle(dup)
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
            args.append(ensure_full_ts(since, "since"))
        if until is not None:
            sql += " AND created_at <= ?"
            args.append(ensure_full_ts(until, "until"))
        sql += " ORDER BY rowid"
        return [_row_to_fill(r) for r in self._conn.execute(sql, args).fetchall()]

    # ── account_snapshot ─────────────────────────────────────────────────
    def open_baseline(self, *, account_id: str, cash: float,
                      at: str | None = None) -> AccountSnapshotRow:
        """开户:写一条 `source='opening'` 基线快照(空仓 + 起始资金)。

        模拟盘/真实账户共用这一个入口——"模拟盘"不是新表,只是 opening 基线
        + 人工回报虚拟成交的约定。两种情形大声拒绝(`DuplicateError`):
          · 已有任何基线(opening/manual/broker)——重复开户会悄悄改写折叠起算点;
          · 已有成交流水——opening 自称"空仓起点、无既往交易",盖在既有 fills 之上
            会让它们被折叠的 since 过滤永久静默剔除(钱凭空消失);既有账请补
            manual/broker 基线,不要开户。
        前置检查给可读错误;真正的守卫是单语句 `INSERT ... WHERE NOT EXISTS`
        (并发双开的 TOCTOU 由 SQL 侧兜底,与 record_fill 的 UNIQUE 同纪律)。
        """
        if cash <= 0:
            raise ValueError(f"起始资金必须为正,收到 {cash!r}")
        existing = self.latest_baseline(account_id)
        if existing is not None:
            raise DuplicateError(
                f"账户 {account_id} 已有基线({existing.as_of}, source={existing.source}),"
                "不可重复开户;如需重置请人工补 manual/broker 基线")
        if self.fills(account_id):
            raise DuplicateError(
                f"账户 {account_id} 已有成交流水,不能再开 opening 基线"
                "(会把既有成交从折叠里静默剔除);既有账请补 manual/broker 基线")
        ts = ensure_full_ts(at, "at") if at else _now()
        marks = ",".join("?" for _ in BASELINE_SOURCES)
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO account_snapshot (account_id, as_of, cash, positions_json,"
                " source, created_at) SELECT ?,?,?,?,?,?"
                " WHERE NOT EXISTS (SELECT 1 FROM account_snapshot"
                f"   WHERE account_id = ? AND source IN ({marks}))"
                " AND NOT EXISTS (SELECT 1 FROM fill WHERE account_id = ?)",
                (account_id, ts, float(cash), "{}", "opening", _now(),
                 account_id, *sorted(BASELINE_SOURCES), account_id))
        if cur.rowcount != 1:       # 并发下另一请求抢先(前置检查的 TOCTOU 兜底)
            raise DuplicateError(
                f"账户 {account_id} 开户失败:已有基线或成交流水(并发抢先?),请刷新核对")
        snap = self.get_snapshot(account_id, ts)
        assert snap is not None                       # 刚写入,必在
        return snap

    def put_snapshot(self, *, account_id: str, as_of: str, cash: float,
                     positions: dict[str, int], source: str = "") -> AccountSnapshotRow:
        """写(或按 (account_id, as_of) 覆盖)一份账户快照。"""
        ensure_full_ts(as_of, "as_of")
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
            args.append(ensure_full_ts(as_of, "as_of"))
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
        if as_of is not None:
            ensure_full_ts(as_of, "as_of")
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
        if base and base.source != "opening":
            # fills 的时间轴是登记时刻(created_at),基线之后**补录**的更早交易
            # (trade_date 早于基线日)若已计入基线,会被重复叠加——查不出对错,
            # 但查得出嫌疑:诚实登记,让人核对,不静默吞掉。
            # opening 基线除外:开仓基线定义上是"空仓起点、无既往交易",
            # 模拟盘补录历史交易日成交是常规操作,不构成重复计账嫌疑
            backfilled = [f for f in rows if f.trade_date.isoformat() < base.as_of[:10]]
            if backfilled:
                shown = ", ".join(f.operation_id for f in backfilled[:3])
                more = "……" if len(backfilled) > 3 else ""
                anomalies.append(
                    f"基线({base.as_of})之后补录了 {len(backfilled)} 笔交易日早于基线的成交"
                    f"(operation_id: {shown}{more});若基线已含这些交易,"
                    "现金/持仓会重复计账,请核对流水或重打基线")
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
            baseline_source=(base.source if base else ""),
            baseline_codes=sorted(c for c, q in (base.positions if base else {}).items() if q),
            anomalies=anomalies)

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
