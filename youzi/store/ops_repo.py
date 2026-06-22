from __future__ import annotations

import json
from datetime import date as Date, datetime as DateTime
from typing import Callable

from youzi.store.db import Database
from youzi.store.models import OpsCandidate, OpsDecision, OpsSession


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


def _parse_date(s: str | None) -> Date | None:
    return Date.fromisoformat(s) if s else None


def _parse_dt(s: str | None) -> DateTime | None:
    return DateTime.fromisoformat(s) if s else None


class OpsRepository:
    """运营全闭环 Repository:会话/候选/决策/成交/持仓/复盘/账户/分析。沿用容器约定 __bool__=True。"""

    def __init__(self, db: Database, clock: Callable[[], DateTime] = DateTime.now) -> None:
        self._db = db
        self._clock = clock

    def __bool__(self) -> bool:
        return True

    # ── 会话 ──
    def create_session(self, s: OpsSession) -> OpsSession:
        created = s.created_at or self._clock()
        cur = self._db.execute(
            "INSERT INTO ops_session (trade_date, regime_read, harness_version, "
            "decision_run_ref, no_trade_reason, note, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (_iso(s.trade_date), s.regime_read, s.harness_version, s.decision_run_ref,
             s.no_trade_reason, s.note, _iso(created)))
        self._db.commit()
        return s.model_copy(update={"session_id": cur.lastrowid, "created_at": created})

    def get_session(self, session_id: int) -> OpsSession | None:
        row = self._db.query_one(
            "SELECT * FROM ops_session WHERE session_id=?", (session_id,))
        return self._row_to_session(row) if row else None

    def session_for_date(self, trade_date: Date) -> OpsSession | None:
        row = self._db.query_one(
            "SELECT * FROM ops_session WHERE trade_date=?", (_iso(trade_date),))
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[OpsSession]:
        rows = self._db.query_all(
            "SELECT * FROM ops_session ORDER BY trade_date DESC LIMIT ?", (limit,))
        return [self._row_to_session(r) for r in rows]

    # ── 候选 ──
    def add_candidates(self, session_id: int,
                       cands: list[OpsCandidate]) -> list[OpsCandidate]:
        out: list[OpsCandidate] = []
        for c in cands:
            cur = self._db.execute(
                "INSERT INTO ops_candidate (session_id, code, name, pattern, rank, "
                "confidence, reason, plan_entry, plan_stop, plan_target, plan_note, raw) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, c.code, c.name, c.pattern, c.rank, c.confidence, c.reason,
                 c.plan_entry, c.plan_stop, c.plan_target, c.plan_note,
                 json.dumps(c.raw, ensure_ascii=False) if c.raw is not None else None))
            out.append(c.model_copy(update={"candidate_id": cur.lastrowid,
                                            "session_id": session_id}))
        self._db.commit()
        return out

    def candidates_for(self, session_id: int) -> list[OpsCandidate]:
        rows = self._db.query_all(
            "SELECT * FROM ops_candidate WHERE session_id=? ORDER BY rank ASC",
            (session_id,))
        return [self._row_to_candidate(r) for r in rows]

    # ── 决策命令 API ──
    def _insert_decision(self, d: OpsDecision) -> OpsDecision:
        created = d.created_at or self._clock()
        cur = self._db.execute(
            "INSERT INTO ops_decision (session_id, candidate_id, code, action, "
            "intent_side, planned_price, planned_qty, status, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d.session_id, d.candidate_id, d.code, d.action, d.intent_side,
             d.planned_price, d.planned_qty, d.status, d.note, _iso(created)))
        self._db.commit()
        return d.model_copy(update={"decision_id": cur.lastrowid, "created_at": created})

    def confirm_decision(self, session_id: int, candidate_id: int, *, intent_side: str,
                         planned_price: float | None = None,
                         planned_qty: int | None = None, note: str = "") -> OpsDecision:
        row = self._db.query_one(
            "SELECT code FROM ops_candidate WHERE candidate_id=?", (candidate_id,))
        if row is None:
            raise ValueError(f"候选 {candidate_id} 不存在")
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=candidate_id, code=row["code"],
            action="confirm", intent_side=intent_side, planned_price=planned_price,
            planned_qty=planned_qty, status="planned", note=note))

    def skip_candidate(self, session_id: int, candidate_id: int, *,
                       note: str = "") -> OpsDecision:
        row = self._db.query_one(
            "SELECT code FROM ops_candidate WHERE candidate_id=?", (candidate_id,))
        if row is None:
            raise ValueError(f"候选 {candidate_id} 不存在")
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=candidate_id, code=row["code"],
            action="skip", status="cancelled", note=note))

    def manual_add(self, session_id: int, code: str, *, intent_side: str,
                   planned_price: float | None = None, planned_qty: int | None = None,
                   note: str = "") -> OpsDecision:
        return self._insert_decision(OpsDecision(
            session_id=session_id, candidate_id=None, code=code, action="manual_add",
            intent_side=intent_side, planned_price=planned_price,
            planned_qty=planned_qty, status="planned", note=note))

    def decisions_for(self, session_id: int) -> list[OpsDecision]:
        rows = self._db.query_all(
            "SELECT * FROM ops_decision WHERE session_id=? ORDER BY decision_id ASC",
            (session_id,))
        return [self._row_to_decision(r) for r in rows]

    # ── row → model ──
    def _row_to_session(self, r) -> OpsSession:
        return OpsSession(
            session_id=r["session_id"], trade_date=_parse_date(r["trade_date"]),
            regime_read=r["regime_read"], harness_version=r["harness_version"],
            decision_run_ref=r["decision_run_ref"], no_trade_reason=r["no_trade_reason"],
            note=r["note"], created_at=_parse_dt(r["created_at"]))

    def _row_to_candidate(self, r) -> OpsCandidate:
        return OpsCandidate(
            candidate_id=r["candidate_id"], session_id=r["session_id"], code=r["code"],
            name=r["name"], pattern=r["pattern"], rank=r["rank"],
            confidence=r["confidence"], reason=r["reason"], plan_entry=r["plan_entry"],
            plan_stop=r["plan_stop"], plan_target=r["plan_target"], plan_note=r["plan_note"],
            raw=json.loads(r["raw"]) if r["raw"] else None)

    def _row_to_decision(self, r) -> OpsDecision:
        return OpsDecision(
            decision_id=r["decision_id"], session_id=r["session_id"],
            candidate_id=r["candidate_id"], code=r["code"], action=r["action"],
            intent_side=r["intent_side"], planned_price=r["planned_price"],
            planned_qty=r["planned_qty"], status=r["status"], note=r["note"],
            created_at=_parse_dt(r["created_at"]))
