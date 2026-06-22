from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, Field


class OpsSession(BaseModel):
    session_id: int | None = None
    trade_date: Date
    regime_read: str = ""
    harness_version: int | None = None       # 软链(D 期)
    decision_run_ref: str | None = None       # 软链(C 期)
    no_trade_reason: str = ""
    note: str = ""
    created_at: DateTime | None = None


class OpsCandidate(BaseModel):
    candidate_id: int | None = None
    session_id: int
    code: str
    name: str = ""
    pattern: str = ""
    rank: int
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""
    plan_entry: float | None = None
    plan_stop: float | None = None
    plan_target: float | None = None
    plan_note: str = ""
    raw: dict | None = None


class OpsDecision(BaseModel):
    decision_id: int | None = None
    session_id: int
    candidate_id: int | None = None
    code: str
    action: str                              # confirm | skip | manual_add | modify
    intent_side: str | None = None           # buy | sell
    planned_price: float | None = None
    planned_qty: int | None = None
    status: str = "planned"                   # planned | executed | cancelled | expired
    note: str = ""
    created_at: DateTime | None = None


class OpsFill(BaseModel):
    fill_id: int | None = None
    decision_id: int | None = None
    position_id: int | None = None
    code: str
    side: str                                 # buy | sell
    price: float
    qty: int
    filled_at: DateTime
    fee: float | None = None
    note: str = ""


class OpsPosition(BaseModel):
    position_id: int | None = None
    code: str
    name: str = ""
    pattern: str = ""
    opened_on: Date
    closed_on: Date | None = None
    status: str = "open"                      # open | closed
    qty_open: int = 0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    origin_decision_id: int | None = None


class OpsReview(BaseModel):
    review_id: int | None = None
    session_id: int | None = None
    position_id: int | None = None
    body: str = ""
    tags: str = ""
    lesson_ref: str | None = None
    created_at: DateTime | None = None


class AccountDaily(BaseModel):
    trade_date: Date
    equity: float | None = None
    cash: float | None = None
    market_value: float | None = None
    realized_pnl_day: float | None = None
    unrealized_pnl: float | None = None
    note: str = ""
