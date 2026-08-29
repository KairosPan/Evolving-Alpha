# tests/test_web_account.py — 账户模块(模拟盘 v1):开户/回报成交表单 + 折叠总览页
"""全离线:tmp live.db(YOUZI_LIVE_DB)+ tmp PIT 快照(YOUZI_SNAPSHOT)。"""
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from youzi_web.app import create_app

D = date(2024, 6, 27)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """tmp live.db + 单日迷你快照(600001 收盘 12.0)。"""
    monkeypatch.setenv("YOUZI_LIVE_DB", str(tmp_path / "live.db"))
    from youzi.data.cache import PITStore
    store = PITStore(tmp_path / "snap")
    store.put("zt", D, pd.DataFrame({"code": ["600001"], "name": ["龙一"],
                                     "boards": [3], "pct": [10.0]}))
    for pool in ("prev", "blowup", "dt"):
        store.put(pool, D, pd.DataFrame())
    store.put_ohlcv("600001", pd.DataFrame({
        "date": [D], "open": [10.0], "high": [12.0], "low": [10.0],
        "close": [12.0], "volume": [1e6]}))
    store.put_calendar([D])
    monkeypatch.setenv("YOUZI_SNAPSHOT", str(tmp_path / "snap"))
    return tmp_path


@pytest.fixture
def client(env):
    return TestClient(create_app())


def _open(client, cash=200_000):
    return client.post("/account/open",
                       data={"account_id": "paper", "cash": cash},
                       follow_redirects=False)


def _fill(client, op="op-1", side="buy", price=10.0, qty=200, fee=0.6,
          code="600001", trade_date="2024-06-27"):
    return client.post("/account/fill", data={
        "account_id": "paper", "operation_id": op, "trade_date": trade_date,
        "code": code, "side": side, "price": price, "qty": qty, "fee": fee},
        follow_redirects=False)


# ── 开户 ─────────────────────────────────────────────────────────────────

def test_unopened_shows_open_form(client):
    r = client.get("/account/overview")
    assert r.status_code == 200
    assert "开设模拟盘账户" in r.text and "opening" in r.text


def test_open_then_overview_absolute_cash(client):
    assert _open(client).status_code == 303
    page = client.get("/account/overview")
    assert "绝对" in page.text                      # 现金口径
    assert "200000.00" in page.text
    assert "opening" in page.text                   # 基线卡


def test_duplicate_open_is_409(client):
    _open(client)
    r = _open(client)
    assert r.status_code == 409 and "已有基线" in r.text


def test_open_nonpositive_cash_is_422(client):
    r = _open(client, cash=-5)
    assert r.status_code == 422


# ── 回报成交 + 折叠展示 ──────────────────────────────────────────────────

def test_fill_flow_positions_price_and_pnl(client):
    _open(client)
    assert _fill(client).status_code == 303
    page = client.get("/account/overview").text
    assert "600001" in page
    assert "12.00" in page                          # 快照现价
    assert "+399.40" in page                        # 浮盈 = 200×12 − (2000+0.6)
    assert "197999.40" in page                      # 现金 = 200000 − 2000.6
    assert "200399.40" in page                      # 总资产 = 现金 + 市值
    assert "成交流水(1" in page


def test_fill_same_operation_id_is_idempotent(client):
    _open(client)
    _fill(client, op="op-x")
    r = _fill(client, op="op-x")                    # 同幂等键重复提交
    from urllib.parse import unquote
    assert r.status_code == 303 and "重复提交" in unquote(r.headers["location"])
    page = client.get("/account/overview").text
    assert "成交流水(1" in page                     # 未重复入账


def test_fill_param_errors_are_422(client):
    _open(client)
    assert _fill(client, side="short").status_code == 422
    assert _fill(client, qty=0).status_code == 422
    assert _fill(client, trade_date="not-a-date").status_code == 422


def test_sell_realizes_pnl(client):
    _open(client)
    _fill(client, op="b1", side="buy", price=10.0, qty=200, fee=0.6)
    _fill(client, op="s1", side="sell", price=12.0, qty=200, fee=1.92)
    page = client.get("/account/overview").text
    assert "+397.48" in page                        # 已实现 = 2400−1.92−2000.6
    assert "空仓" in page                           # 清仓后持仓表空


def test_without_snapshot_prices_degrade_honestly(client, monkeypatch):
    _open(client)
    _fill(client)
    monkeypatch.delenv("YOUZI_SNAPSHOT")
    page = client.get("/account/overview").text
    assert "现价/浮盈不可用" in page
    assert "—" in page                              # 现价/浮盈栏诚实空


def test_shell_marks_account_feature_active(client):
    page = client.get("/account/overview").text
    assert 'class="rail-item active"' in page or "rail-item active" in page


# ── 评审修复回归 ─────────────────────────────────────────────────────────

def test_fill_same_op_different_fields_is_409_not_fake_ok(client):
    """旧 operation_id + 不同字段 ≠ 重试:必须报错,不能绿字假确认吞掉新成交。"""
    _open(client)
    _fill(client, op="op-y", price=10.0)
    r = _fill(client, op="op-y", price=11.0)
    assert r.status_code == 409 and "已被另一笔不同成交占用" in r.text


def test_fill_requires_opened_account(client):
    r = _fill(client)                                # 未开户直接回报成交
    assert r.status_code == 409 and "请先开户" in r.text


def test_cross_site_post_is_rejected(client):
    r = client.post("/account/open", data={"account_id": "paper", "cash": 1000},
                    headers={"Sec-Fetch-Site": "cross-site"},
                    follow_redirects=False)
    assert r.status_code == 403 and "跨站" in r.text


def test_fill_bad_code_is_422(client):
    _open(client)
    assert _fill(client, code="60051").status_code == 422      # 5 位
    assert _fill(client, code="60051a").status_code == 422


def test_baseline_sourced_position_unreal_is_honest_blank(client, env):
    """broker 基线持仓无成本价:浮盈留空 + 合计打 *,不把整个市值当利润。"""
    from youzi.store.account_repo import AccountRepo
    from youzi.store.db import connect
    AccountRepo(connect()).put_snapshot(
        account_id="paper", as_of="2024-06-26T15:00:00", cash=50_000.0,
        positions={"600001": 200}, source="broker")
    page = client.get("/account/overview").text
    assert "+0.00<small>*</small>" in page            # 浮盈合计不含基线持仓,打 * 标记
    assert "勿据此算浮盈" in page                     # fold 的 anomaly 上墙
    assert "+2400.00" not in page                     # 市值 2400 显示,但绝不冒充浮盈
