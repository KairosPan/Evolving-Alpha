# youzi_web/features/market/router.py
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from youzi.data.snapshot_source import SnapshotMissingError
from youzi_mcp import market_core as core
from youzi_web.features.market import service

router = APIRouter()


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": msg})


# ── JSON API(供页面 HTMX 与任何外部消费方) ────────────────────────────────

@router.get("/api/market/days")
def api_days():
    return {"days": service.days()}


@router.get("/api/market/brief")
def api_brief(day: str | None = None):
    d = service.pick_day(day)
    if d is None:
        return _err(404, "未配置快照(YOUZI_SNAPSHOT)或快照为空")
    try:
        return service.brief(d)
    except SnapshotMissingError as exc:
        return _err(404, str(exc))


@router.get("/api/market/candidates")
def api_candidates(day: str | None = None, min_boards: int = 1):
    d = service.pick_day(day)
    if d is None:
        return _err(404, "未配置快照(YOUZI_SNAPSHOT)或快照为空")
    try:
        return service.candidates(d, min_boards=min_boards)
    except SnapshotMissingError as exc:
        return _err(404, str(exc))


@router.get("/api/market/bars")
def api_bars(symbol: str, start: str, end: str):
    market, code = core.parse_symbol(symbol)
    if (e := core.market_error(market)) is not None:
        return _err(400, e)
    if (e := core.validate_cn_code(code)) is not None:
        return _err(400, e)
    try:
        return service.bars(code, Date.fromisoformat(start), Date.fromisoformat(end))
    except ValueError as exc:
        return _err(400, f"参数错误:{exc}")


# ── 页面与片段 ────────────────────────────────────────────────────────────

def _shell(request: Request, extra: dict) -> dict:
    return {"request": request, "features": request.app.state.features,
            "active_feature_id": "market", "active_path": "/market/board", **extra}


@router.get("/market/board")
def board_page(request: Request, day: str | None = None, min_boards: int = 1):
    try:
        ctx = service.board_context(day, min_boards=min_boards)
        ctx["error"] = None
    except SnapshotMissingError as exc:
        ctx = {"no_snapshot": False, "days": service.days(), "day": day,
               "min_boards": min_boards, "brief": None, "cands": [], "error": str(exc)}
    return request.app.state.templates.TemplateResponse(
        request, "board.html", _shell(request, ctx))


@router.get("/market/kline")
def kline_fragment(request: Request, symbol: str, day: str):
    market, code = core.parse_symbol(symbol)
    if (e := core.market_error(market)) is not None or \
       (e := core.validate_cn_code(code)) is not None:
        return _err(400, e)
    avail = service.days()
    start = Date.fromisoformat(avail[0]) if avail else Date.fromisoformat(day)
    payload = service.bars(code, start, Date.fromisoformat(day))
    return request.app.state.templates.TemplateResponse(
        request, "_kline.html",
        {"request": request, "payload": payload,
         "geo": service.kline_geometry(payload["bars"])})
