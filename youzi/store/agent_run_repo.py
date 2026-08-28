# youzi/store/agent_run_repo.py
"""AgentRun 仓储:一次 LLM 建议运行的生命周期记录。

状态机 **单向不可逆**:

    pending ──> running ──> succeeded ──> (adopted_at 打戳)
       │           │
       └───────────┴──> failed

非法转移(succeeded→running、failed→succeeded、重复 adopt……)一律抛
`IllegalTransitionError`,**不静默 no-op**——co-pilot 的审计链靠这条不可逆性成立。

强制在**双侧**:
  · SQL 侧 `UPDATE ... WHERE run_id=? AND status IN (合法前态)`,rowcount 判定;
  · Python 侧先读当前态查 `_ALLOWED` 表,给出可读错误。
并发下(两进程同时 mark)SQL 侧的 rowcount=0 兜住 Python 侧的 TOCTOU。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date as Date, datetime as DateTime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from youzi.store.errors import IllegalTransitionError, NotFoundError

AgentRunStatus = Literal["pending", "running", "succeeded", "failed"]

# 合法后继态;空集合=终态
_ALLOWED: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "failed"}),
    "running": frozenset({"succeeded", "failed"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
}

_COLUMNS = (
    "run_id", "trade_date", "market_as_of", "snapshot_ref", "strategy_id",
    "harness_snapshot_ref", "account_id", "account_context_json", "model",
    "temperature", "prompt_fingerprint", "status", "raw_output",
    "parsed_output_json", "error", "created_at", "finished_at", "adopted_at",
)


class AgentRun(BaseModel):
    """一次 agent 运行的不可变读模型(frozen;写走 repo 方法,不改对象)。"""
    model_config = ConfigDict(frozen=True)
    run_id: str
    trade_date: Date
    market_as_of: str | None = None       # ISO datetime;市场快照时点(防未来函数审计)
    snapshot_ref: str | None = None       # 市场快照来源标识(源类型@日期)
    strategy_id: str
    harness_snapshot_ref: str | None = None   # 解析后的 H 版本("seed" / "snapshot:3")
    account_id: str = ""
    account_context_json: str | None = None   # **冻结**账户上下文;此后校验只认这份
    model: str = ""
    temperature: float | None = None
    prompt_fingerprint: str = ""
    status: AgentRunStatus
    raw_output: str | None = None
    parsed_output_json: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None
    adopted_at: str | None = None

    def account_context(self) -> dict:
        """冻结账户上下文 → dict(未写入/损坏 → 空 dict)。"""
        if not self.account_context_json:
            return {}
        try:
            d = json.loads(self.account_context_json)
        except json.JSONDecodeError:
            return {}
        return d if isinstance(d, dict) else {}

    def parsed_output(self) -> dict:
        """结构化决策 → dict(未写入/损坏 → 空 dict)。"""
        if not self.parsed_output_json:
            return {}
        try:
            d = json.loads(self.parsed_output_json)
        except json.JSONDecodeError:
            return {}
        return d if isinstance(d, dict) else {}


def _now() -> str:
    return DateTime.now().isoformat(timespec="seconds")


def _row_to_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun.model_validate({k: row[k] for k in _COLUMNS})


def stamp_adopted(conn: sqlite3.Connection, run_id: str, at: str | None = None) -> str:
    """给 succeeded 且未采纳的运行打 adopted_at 戳。**不自带事务**。

    模块级函数而非方法:`OpsRepository.adopt_run` 需要把"打戳 + 建 ops_session +
    写候选"放进**同一个事务**(sqlite3 的 `with conn` 不可嵌套,嵌套会提前 commit),
    故把这段无事务的原子写抽出来,给两个调用方共用同一份前置条件语义。
    """
    ts = at or _now()
    cur = conn.execute(
        "UPDATE agent_run SET adopted_at = ? WHERE run_id = ?"
        " AND status = 'succeeded' AND adopted_at IS NULL", (ts, run_id))
    if cur.rowcount != 1:
        raise IllegalTransitionError(
            f"采纳失败:运行不存在 / 非 succeeded / 已采纳过 (run_id={run_id})")
    return ts


class AgentRunRepository:
    """agent_run 表的纯仓储。持有一个 sqlite3 连接,不做业务判断。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── 读 ────────────────────────────────────────────────────────────────
    def get(self, run_id: str) -> AgentRun | None:
        row = self._conn.execute(
            "SELECT * FROM agent_run WHERE run_id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row else None

    def require(self, run_id: str) -> AgentRun:
        """get 的强制版:不存在 → NotFoundError(web 层映射 404)。"""
        run = self.get(run_id)
        if run is None:
            raise NotFoundError(f"agent_run 不存在: {run_id}")
        return run

    def list_by_date(self, trade_date: Date) -> list[AgentRun]:
        """某交易日的全部运行,新 → 旧。"""
        rows = self._conn.execute(
            "SELECT * FROM agent_run WHERE trade_date = ? "
            "ORDER BY created_at DESC, run_id DESC",
            (trade_date.isoformat(),)).fetchall()
        return [_row_to_run(r) for r in rows]

    # ── 写 ────────────────────────────────────────────────────────────────
    def create(self, *, trade_date: Date, strategy_id: str,
               run_id: str | None = None,
               market_as_of: str | None = None, snapshot_ref: str | None = None,
               harness_snapshot_ref: str | None = None, account_id: str = "",
               account_context: dict | None = None, model: str = "",
               temperature: float | None = None,
               prompt_fingerprint: str = "") -> AgentRun:
        """建一条 pending 运行。先落 pending 再干活 → 进程崩溃也留下痕迹。"""
        rid = run_id or uuid.uuid4().hex
        ctx = (json.dumps(account_context, ensure_ascii=False)
               if account_context is not None else None)
        with self._conn:
            self._conn.execute(
                "INSERT INTO agent_run (run_id, trade_date, market_as_of, snapshot_ref,"
                " strategy_id, harness_snapshot_ref, account_id, account_context_json,"
                " model, temperature, prompt_fingerprint, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?)",
                (rid, trade_date.isoformat(), market_as_of, snapshot_ref, strategy_id,
                 harness_snapshot_ref, account_id, ctx, model, temperature,
                 prompt_fingerprint, _now()))
        return self.require(rid)

    def _transition(self, run_id: str, target: AgentRunStatus, sets: dict) -> AgentRun:
        """通用状态转移:Python 侧查表 + SQL 侧 WHERE 前态 双重强制。"""
        current = self.require(run_id)
        if target not in _ALLOWED[current.status]:
            raise IllegalTransitionError(
                f"非法状态转移 {current.status} → {target} (run_id={run_id})")
        legal_from = sorted(s for s, nxt in _ALLOWED.items() if target in nxt)
        assign = "".join(f", {k} = ?" for k in sets)      # sets 可为空(如 mark_running)
        placeholders = ", ".join("?" for _ in legal_from)
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE agent_run SET status = ?{assign}"
                f" WHERE run_id = ? AND status IN ({placeholders})",
                (target, *sets.values(), run_id, *legal_from))
        if cur.rowcount != 1:       # 并发下前态已被别人改走(Python 侧 TOCTOU 兜底)
            raise IllegalTransitionError(
                f"状态转移失败(并发改动?) → {target} (run_id={run_id})")
        return self.require(run_id)

    def mark_running(self, run_id: str) -> AgentRun:
        return self._transition(run_id, "running", {})

    def set_prompt_fingerprint(self, run_id: str, fingerprint: str) -> None:
        """补写提示指纹(纯元数据,与状态机正交)。

        指纹只有在提示渲染完成后才算得出,而运行必须**先**落 pending 再干活,
        故留这条独立的元数据补写口,而不是把状态机转移撑大。
        """
        with self._conn:
            self._conn.execute(
                "UPDATE agent_run SET prompt_fingerprint = ? WHERE run_id = ?",
                (fingerprint, run_id))

    def mark_succeeded(self, run_id: str, *, raw_output: str = "",
                       parsed_output: dict | None = None) -> AgentRun:
        return self._transition(run_id, "succeeded", {
            "raw_output": raw_output,
            "parsed_output_json": (json.dumps(parsed_output, ensure_ascii=False)
                                   if parsed_output is not None else None),
            "finished_at": _now(),
        })

    def mark_failed(self, run_id: str, *, error: str,
                    raw_output: str | None = None) -> AgentRun:
        return self._transition(run_id, "failed", {
            "error": error, "raw_output": raw_output, "finished_at": _now()})

    def mark_adopted(self, run_id: str, *, at: str | None = None) -> AgentRun:
        """采纳打戳。**仅 succeeded 且未采纳**可打;重复采纳 → IllegalTransitionError。

        不改 status(采纳是 succeeded 之上的正交标记),故走独立的
        `WHERE status='succeeded' AND adopted_at IS NULL` 条件写。
        """
        run = self.require(run_id)          # 不存在 → NotFoundError(404 而非 409)
        if run.status != "succeeded":
            raise IllegalTransitionError(
                f"仅 succeeded 运行可采纳,当前 status={run.status} (run_id={run_id})")
        if run.adopted_at is not None:
            raise IllegalTransitionError(f"运行已采纳过: {run_id} @ {run.adopted_at}")
        with self._conn:
            stamp_adopted(self._conn, run_id, at)
        return self.require(run_id)
