# youzi/store/ops_repo.py
"""作战 session 仓储:ops_session / ops_candidate / decision。

`ops_session` = "某账户某交易日采纳的那一份建议单",由 `UNIQUE(account_id, trade_date)`
把"一天一单"钉进 schema——重复采纳同日 → `DuplicateError`,**报错给调用方**,
不静默覆盖(co-pilot 的人工确认链不能被悄悄改写)。

`decision` = 人对某候选的确认动作(buy/skip/watch),`UNIQUE(candidate_id)`
保证一个候选只被确认一次。**决策不等于成交**——成交另走 `fill`。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date as Date, datetime as DateTime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from youzi.store.agent_run_repo import stamp_adopted
from youzi.store.errors import DuplicateError, NotFoundError

DecisionAction = Literal["buy", "skip", "watch"]
CheckStatus = Literal["ok", "blocked", "unknown"]


class OpsCandidate(BaseModel):
    """建议单上的一个候选(frozen 读模型)。

    check_status:`ok`=确定性校验通过;`blocked`=校验不过(**标记保留、不静默丢弃**,
    人仍看得见系统为何否掉);`unknown`=缺数据无法判定(诚实的第三态,不当作通过)。
    """
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    session_id: str
    rank: int
    code: str
    name: str = ""
    pattern: str = ""
    score: float | None = None
    reason: str = ""
    plan_json: str | None = None
    check_status: CheckStatus
    check_json: str | None = None
    created_at: str

    def plan(self) -> dict:
        return _loads_dict(self.plan_json)

    def check(self) -> dict:
        return _loads_dict(self.check_json)


class OpsSession(BaseModel):
    """某账户某交易日的建议单(frozen 读模型)。"""
    model_config = ConfigDict(frozen=True)
    session_id: str
    account_id: str
    trade_date: Date
    agent_run_id: str
    created_at: str
    candidates: list[OpsCandidate] = []


class Decision(BaseModel):
    """人工确认记录(frozen 读模型)。"""
    model_config = ConfigDict(frozen=True)
    decision_id: str
    session_id: str
    candidate_id: str
    action: DecisionAction
    note: str = ""
    confirmed_at: str


_CAND_COLS = ("candidate_id", "session_id", "rank", "code", "name", "pattern",
              "score", "reason", "plan_json", "check_status", "check_json", "created_at")
_SESSION_COLS = ("session_id", "account_id", "trade_date", "agent_run_id", "created_at")
_DECISION_COLS = ("decision_id", "session_id", "candidate_id", "action", "note",
                  "confirmed_at")


def _loads_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return d if isinstance(d, dict) else {}


def _now() -> str:
    return DateTime.now().isoformat(timespec="seconds")


def _dumps(d: dict | None) -> str | None:
    return json.dumps(d, ensure_ascii=False) if d is not None else None


class OpsRepository:
    """ops_session / ops_candidate / decision 的纯仓储。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── 写 ────────────────────────────────────────────────────────────────
    def adopt_run(self, *, run_id: str, account_id: str, trade_date: Date,
                  candidates: list[dict], session_id: str | None = None) -> OpsSession:
        """采纳一次运行:打 adopted_at 戳 + 建 session + 写候选,**单事务全成或全不成**。

        `candidates` 每项:code/name/pattern/score/reason/plan(dict)/check_status/check(dict)。
        前置条件(succeeded 且未采纳)由 `stamp_adopted` 在 SQL 侧强制;
        `UNIQUE(account_id, trade_date)` 冲突 → `DuplicateError`(事务回滚,戳也不落)。
        """
        sid = session_id or uuid.uuid4().hex
        ts = _now()
        try:
            with self._conn:
                stamp_adopted(self._conn, run_id, ts)
                self._conn.execute(
                    "INSERT INTO ops_session (session_id, account_id, trade_date,"
                    " agent_run_id, created_at) VALUES (?,?,?,?,?)",
                    (sid, account_id, trade_date.isoformat(), run_id, ts))
                for rank, c in enumerate(candidates):
                    self._conn.execute(
                        "INSERT INTO ops_candidate (candidate_id, session_id, rank, code,"
                        " name, pattern, score, reason, plan_json, check_status, check_json,"
                        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uuid.uuid4().hex, sid, rank, str(c["code"]),
                         str(c.get("name") or ""), str(c.get("pattern") or ""),
                         c.get("score"), str(c.get("reason") or ""),
                         _dumps(c.get("plan")), c.get("check_status") or "unknown",
                         _dumps(c.get("check")), ts))
        except sqlite3.IntegrityError as e:
            raise DuplicateError(
                f"账户 {account_id} 在 {trade_date} 已有建议单(或候选 code 重复): {e}") from e
        return self.require_session(sid)

    def confirm(self, *, candidate_id: str, action: DecisionAction,
                note: str = "", decision_id: str | None = None) -> Decision:
        """人工确认一个候选。同一候选重复确认 → `DuplicateError`(UNIQUE(candidate_id))。"""
        cand = self.get_candidate(candidate_id)
        if cand is None:
            raise NotFoundError(f"候选不存在: {candidate_id}")
        did = decision_id or uuid.uuid4().hex
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO decision (decision_id, session_id, candidate_id, action,"
                    " note, confirmed_at) VALUES (?,?,?,?,?,?)",
                    (did, cand.session_id, candidate_id, action, note, _now()))
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"候选已确认过: {candidate_id}") from e
        row = self._conn.execute(
            "SELECT * FROM decision WHERE decision_id = ?", (did,)).fetchone()
        return Decision.model_validate({k: row[k] for k in _DECISION_COLS})

    # ── 读 ────────────────────────────────────────────────────────────────
    def get_candidate(self, candidate_id: str) -> OpsCandidate | None:
        row = self._conn.execute(
            "SELECT * FROM ops_candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return OpsCandidate.model_validate({k: row[k] for k in _CAND_COLS}) if row else None

    def candidates(self, session_id: str) -> list[OpsCandidate]:
        rows = self._conn.execute(
            "SELECT * FROM ops_candidate WHERE session_id = ? ORDER BY rank",
            (session_id,)).fetchall()
        return [OpsCandidate.model_validate({k: r[k] for k in _CAND_COLS}) for r in rows]

    def get_session(self, session_id: str) -> OpsSession | None:
        row = self._conn.execute(
            "SELECT * FROM ops_session WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return OpsSession.model_validate(
            {**{k: row[k] for k in _SESSION_COLS},
             "candidates": self.candidates(session_id)})

    def require_session(self, session_id: str) -> OpsSession:
        s = self.get_session(session_id)
        if s is None:
            raise NotFoundError(f"建议单不存在: {session_id}")
        return s

    def session_for(self, account_id: str, trade_date: Date) -> OpsSession | None:
        row = self._conn.execute(
            "SELECT session_id FROM ops_session WHERE account_id = ? AND trade_date = ?",
            (account_id, trade_date.isoformat())).fetchone()
        return self.get_session(row["session_id"]) if row else None

    def decisions(self, session_id: str) -> list[Decision]:
        rows = self._conn.execute(
            "SELECT * FROM decision WHERE session_id = ? ORDER BY confirmed_at",
            (session_id,)).fetchall()
        return [Decision.model_validate({k: r[k] for k in _DECISION_COLS}) for r in rows]
