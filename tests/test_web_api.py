# tests/test_web_api.py
"""/api/* 冒烟(FastAPI TestClient + 离线注入的 service)。

web 层只做参数解析 → 调 service → 序列化,故这里只验:路由挂上了、
参数进得去、领域异常翻成了正确的 HTTP 码。业务规则本身在领域层测。
"""
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeSource
from youzi.application.live_decision import LiveDecisionService
from youzi.llm.client import MockLLMClient
from youzi.store.account_repo import AccountRepo
from youzi.store.agent_run_repo import AgentRunRepository
from youzi.store.db import connect
from youzi.store.ops_repo import OpsRepository
from youzi_web.api import get_service
from youzi_web.app import create_app

D = date(2024, 6, 26)
PICK = ('{"regime_read":"主升","candidates":[{"code":"600000","pattern":"highest_board",'
        '"reason":"最高板","confidence":0.8}]}')


def _source():
    frames = {("zt", D): pd.DataFrame({"code": ["600000"], "name": ["甲"],
                                       "boards": [3], "pct": [10.0]}),
              ("blowup", D): pd.DataFrame(), ("dt", D): pd.DataFrame(),
              ("prev", D): pd.DataFrame()}
    ohlcv = {"600000": pd.DataFrame({"date": [D], "open": [10.0], "high": [11.0],
                                     "low": [9.5], "close": [11.0], "volume": [1]})}
    return FakeSource(frames, [D], ohlcv)


@pytest.fixture
def client_and_service():
    conn = connect(":memory:")
    svc = LiveDecisionService(
        source=_source(), llm=MockLLMClient([PICK, PICK]),
        agent_runs=AgentRunRepository(conn), accounts=AccountRepo(conn),
        ops=OpsRepository(conn), model="mock")
    app = create_app()
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app), svc


@pytest.fixture
def client(client_and_service):
    return client_and_service[0]


def _run(client, strategy="seed", account="A"):
    return client.post("/api/agent-runs", json={
        "trade_date": "2024-06-26", "strategy_version": strategy, "account_id": account})


def test_existing_pages_still_work(client):
    """API 挂上去不能破坏 FE 外壳(单向依赖、零回归)。"""
    assert client.get("/research/harness").status_code == 200
    assert client.get("/", follow_redirects=False).headers["location"] == "/research/harness"


def test_create_and_get_agent_run(client):
    r = _run(client)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "succeeded" and body["trade_date"] == "2024-06-26"
    assert body["harness_snapshot_ref"] == "seed"
    assert body["parsed_output"]["decision"]["candidates"][0]["code"] == "600000"
    assert body["account_context"]["account_id"] == "A"

    got = client.get(f"/api/agent-runs/{body['run_id']}")
    assert got.status_code == 200 and got.json()["run_id"] == body["run_id"]


def test_unknown_run_is_404(client):
    r = client.get("/api/agent-runs/nope")
    assert r.status_code == 404 and r.json()["error"] == "NotFoundError"


def test_unknown_strategy_is_422(client):
    r = _run(client, strategy="bogus")
    assert r.status_code == 422 and r.json()["error"] == "StrategyNotFoundError"


def test_bad_request_body_is_422(client):
    assert client.post("/api/agent-runs", json={"trade_date": "not-a-date",
                                                "account_id": "A"}).status_code == 422
    assert client.post("/api/agent-runs", json={"trade_date": "2024-06-26",
                                                "account_id": ""}).status_code == 422


def test_adopt_then_conflict(client):
    run_id = _run(client).json()["run_id"]
    a = client.post(f"/api/agent-runs/{run_id}/adopt")
    assert a.status_code == 201
    sess = a.json()
    assert [c["code"] for c in sess["candidates"]] == ["600000"]
    assert sess["candidates"][0]["check"]["limit_price_next"] == pytest.approx(12.1)

    assert client.post(f"/api/agent-runs/{run_id}/adopt").status_code == 409
    other = _run(client).json()["run_id"]            # 同账户同日第二次采纳
    assert client.post(f"/api/agent-runs/{other}/adopt").status_code == 409
    assert client.post("/api/agent-runs/nope/adopt").status_code == 404


def test_fills_are_idempotent_over_http(client):
    payload = {"operation_id": "op-1", "account_id": "A", "trade_date": "2024-06-26",
               "code": "600000", "side": "buy", "price": 11.0, "qty": 100, "fee": 2.0}
    first = client.post("/api/accounts/fills", json=payload)
    assert first.status_code == 201 and first.json()["created"] is True
    again = client.post("/api/accounts/fills", json=payload)
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["fill"]["fill_id"] == first.json()["fill"]["fill_id"]


def test_fill_body_validation(client):
    bad = {"operation_id": "x", "account_id": "A", "trade_date": "2024-06-26",
           "code": "600000", "side": "short", "price": 11.0, "qty": 100}
    assert client.post("/api/accounts/fills", json=bad).status_code == 422
    bad2 = {**bad, "side": "buy", "qty": 0}
    assert client.post("/api/accounts/fills", json=bad2).status_code == 422


def test_accounts_current_and_positions_fold_from_fills(client):
    client.post("/api/accounts/fills", json={
        "operation_id": "op-1", "account_id": "A", "trade_date": "2024-06-26",
        "code": "600000", "side": "buy", "price": 10.0, "qty": 200, "fee": 0.0})
    cur = client.get("/api/accounts/current?account_id=A").json()
    assert cur["positions"][0]["qty"] == 200
    assert cur["cash"] == pytest.approx(-2000.0)
    assert cur["is_absolute_cash"] is False           # 无基线 → 明说是净变动口径

    pos = client.get("/api/accounts/positions?account_id=A").json()
    assert pos["positions"] == cur["positions"] and pos["anomalies"] == []
    assert client.get("/api/accounts/current").status_code == 422    # 缺 account_id


def test_market_snapshot(client):
    r = client.get("/api/market/snapshot?date=2024-06-26")
    assert r.status_code == 200
    body = r.json()
    assert body["universe"]["limit_up"] == 1
    assert body["state"]["max_board_height"] == 3
    assert body["as_of"] == "2024-06-26T15:00:00"
    assert client.get("/api/market/snapshot").status_code == 422     # 缺 date


def test_strategies(client):
    r = client.get("/api/strategies")
    assert r.status_code == 200 and r.json()[0]["version"] == "seed"


def test_failed_run_is_recorded_and_cannot_be_adopted():
    class BoomLLM:
        def complete(self, system, user):
            raise RuntimeError("上游 502")

    conn = connect(":memory:")
    svc = LiveDecisionService(source=_source(), llm=BoomLLM(),
                              agent_runs=AgentRunRepository(conn),
                              accounts=AccountRepo(conn), ops=OpsRepository(conn))
    app = create_app()
    app.dependency_overrides[get_service] = lambda: svc
    client = TestClient(app)
    r = _run(client)
    assert r.status_code == 201 and r.json()["status"] == "failed"
    assert "上游 502" in r.json()["error"]
    assert client.post(f"/api/agent-runs/{r.json()['run_id']}/adopt").status_code == 409
