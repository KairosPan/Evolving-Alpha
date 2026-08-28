# youzi_web/api.py
"""live 决策 JSON API。

纪律(承接 FE-0):**领域 `youzi/` 零改动、单向依赖** —— 本模块只 import `youzi`,
`youzi` 永不 import `youzi_web`。web 层**不做业务判断**,只负责
参数解析 → 调 service → 序列化;所有规则(状态机、唯一性、可成交性校验)
都在领域/仓储层,web 只把领域异常翻成 HTTP 码:

    非法状态转移 / 唯一约束冲突 → 409
    找不到                      → 404
    参数或校验失败              → 422

service 经 FastAPI 依赖注入(`get_service`)取得,测试用
`app.dependency_overrides[get_service]` 注入离线 service(FakeSource + MockLLM)。
"""
from __future__ import annotations

import os
from datetime import date as Date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from youzi.application.live_decision import LiveDecisionService, StrategyNotFoundError
from youzi.store.account_repo import AccountRepo, ensure_full_ts
from youzi.store.agent_run_repo import AgentRunRepository
from youzi.store.db import connect
from youzi.store.errors import DuplicateError, IllegalTransitionError, NotFoundError
from youzi.store.ops_repo import OpsRepository

router = APIRouter(prefix="/api", tags=["live"])


# ── 依赖:每请求一条连接 ─────────────────────────────────────────────────
def build_service() -> LiveDecisionService:
    """从环境装配默认 service(每请求新建 sqlite 连接,避免跨线程共享)。

    数据源:`YOUZI_SNAPSHOT`(PIT 快照目录)→ 离线 `SnapshotSource`;
    否则 `AkshareSource`(真实取数)。LLM:`DEEPSEEK_API_KEY` → `DeepSeekClient`。
    **lazy import**:没装 akshare/openai 的离线环境不该在 import 期就炸。
    """
    from youzi.harness.snapshot import SnapshotStore

    conn = connect()
    snap_dir = os.environ.get("YOUZI_SNAPSHOT")
    if snap_dir:
        from youzi.data.cache import PITStore
        from youzi.data.snapshot_source import SnapshotSource
        source = SnapshotSource(PITStore(snap_dir))
    else:
        from youzi.data.source import AkshareSource
        source = AkshareSource()
    from youzi.llm.client import DeepSeekClient
    model = os.environ.get("YOUZI_LLM_MODEL", "deepseek-chat")
    llm = DeepSeekClient(model=model)
    store_dir = os.environ.get("YOUZI_HARNESS_SNAPSHOTS")
    return LiveDecisionService(
        source=source, llm=llm, agent_runs=AgentRunRepository(conn),
        accounts=AccountRepo(conn), ops=OpsRepository(conn),
        snapshot_store=SnapshotStore(Path(store_dir)) if store_dir else None,
        model=model)


def get_service() -> LiveDecisionService:
    """FastAPI 依赖。测试经 `app.dependency_overrides[get_service]` 注入离线实例。"""
    return build_service()


Service = Depends(get_service)


# ── 请求体 ───────────────────────────────────────────────────────────────
class AgentRunRequest(BaseModel):
    trade_date: Date
    strategy_version: str = "seed"
    account_id: str = Field(min_length=1)


class FillRequest(BaseModel):
    operation_id: str = Field(min_length=1)     # 幂等键:重复提交不重复入账
    account_id: str = Field(min_length=1)
    trade_date: Date
    code: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    qty: int = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
    decision_id: str | None = None


# ── 序列化 ───────────────────────────────────────────────────────────────
def _run_json(run) -> dict:
    d = run.model_dump(mode="json")
    d["account_context"] = run.account_context()
    d["parsed_output"] = run.parsed_output()
    return d


def _session_json(session) -> dict:
    d = session.model_dump(mode="json")
    for c, row in zip(d["candidates"], session.candidates):
        c["plan"] = row.plan()
        c["check"] = row.check()
    return d


# ── 端点 ─────────────────────────────────────────────────────────────────
@router.post("/agent-runs", status_code=201)
def create_agent_run(body: AgentRunRequest, svc: LiveDecisionService = Service) -> dict:
    """跑一次建议。LLM 失败会落 failed 的 AgentRun 并 201 返回(失败也是记录)。"""
    run = svc.run(body.trade_date, body.strategy_version, body.account_id)
    return _run_json(run)


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: str, svc: LiveDecisionService = Service) -> dict:
    return _run_json(svc.get_run(run_id))


@router.post("/agent-runs/{run_id}/adopt", status_code=201)
def adopt_agent_run(run_id: str, svc: LiveDecisionService = Service) -> dict:
    """采纳 → 建议单。非 succeeded / 重复采纳 / 同日已有单 → 409。"""
    return _session_json(svc.adopt(run_id))


def _validated_as_of(as_of: str | None) -> str | None:
    """`as_of` 必须是含时间部分的完整 ISO datetime,日期粒度会静默错账 → 422。"""
    if as_of is None:
        return None
    try:
        return ensure_full_ts(as_of, "as_of")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/accounts/current")
def account_current(account_id: str = Query(min_length=1), as_of: str | None = None,
                    svc: LiveDecisionService = Service) -> dict:
    """账户现况(现金/持仓/异常)。全部由 fills 折叠而来,非第二份权威表。"""
    view = svc.account_view(account_id, as_of=_validated_as_of(as_of))
    d = view.model_dump(mode="json")
    d["is_absolute_cash"] = view.is_absolute_cash
    return d


@router.get("/accounts/positions")
def account_positions(account_id: str = Query(min_length=1), as_of: str | None = None,
                      svc: LiveDecisionService = Service) -> dict:
    view = svc.account_view(account_id, as_of=_validated_as_of(as_of))
    return {"account_id": account_id, "as_of": as_of,
            "positions": [p.model_dump(mode="json") for p in view.positions],
            "anomalies": list(view.anomalies)}


@router.post("/accounts/fills")
def create_fill(body: FillRequest, svc: LiveDecisionService = Service) -> JSONResponse:
    """回报成交。幂等:同 operation_id 重复提交 → 200 + 已有记录(新建为 201)。"""
    fill, created = svc.record_fill(**body.model_dump())
    return JSONResponse(status_code=201 if created else 200,
                        content={"created": created, "fill": fill.model_dump(mode="json")})


@router.get("/market/snapshot")
def market_snapshot(date: Date, svc: LiveDecisionService = Service) -> dict:
    """某交易日的冻结市场事实(经 GuardedSource,不可越界取未来)。"""
    return svc.market_snapshot(date)


@router.get("/strategies")
def strategies(svc: LiveDecisionService = Service) -> list[dict]:
    return svc.list_strategies()


# ── 领域异常 → HTTP ──────────────────────────────────────────────────────
def _err(status: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": type(exc).__name__, "detail": str(exc)})


def install_api(app: FastAPI) -> None:
    """把 API 路由 + 领域异常映射装进 app。"""
    app.include_router(router)
    app.add_exception_handler(
        NotFoundError, lambda request, exc: _err(404, exc))
    app.add_exception_handler(
        IllegalTransitionError, lambda request, exc: _err(409, exc))
    app.add_exception_handler(
        DuplicateError, lambda request, exc: _err(409, exc))
    app.add_exception_handler(
        StrategyNotFoundError, lambda request, exc: _err(422, exc))


__all__ = ["router", "install_api", "get_service", "build_service"]
