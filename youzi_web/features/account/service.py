# youzi_web/features/account/service.py
"""账户模块读模型:live.db 折叠视图 + 快照现价 enrich(纯展示,不落任何派生表)。

模拟盘约定(v1):account_id 默认 `paper`;开户 = opening 基线;
成交 = 人工回报虚拟回报,与真实成交走同一 `record_fill`(operation_id 幂等)。
"""
from __future__ import annotations

import uuid
from datetime import date as Date
from pathlib import Path

from youzi.data.cache import PITStore
from youzi.data.snapshot_source import SnapshotMissingError, SnapshotSource
from youzi.data.source import GuardedSource
from youzi.eval.fill import CostModel
from youzi.replay.firewall import AsOfGuard
from youzi.store.account_repo import AccountRepo
from youzi.store.db import connect
# 只读复用市场模块的快照定位(snapshot_root/pick_day),避免两份漂移的取数逻辑
from youzi_web.features.market import service as market_service

PAPER_ACCOUNT = "paper"
_COST = CostModel()          # 表单费用预估用默认费率(佣金双边 3bp、印花税卖侧 5bp)


def repo() -> AccountRepo:
    """每请求新建 live.db 连接(与 youzi_web/api.py 同纪律,不跨请求共享)。"""
    return AccountRepo(connect())


def _close_at(code: str, day: Date) -> float | None:
    """code 在 day 的收盘价(经防火墙;缺数/停牌/无快照 → 诚实 None)。"""
    root = market_service.snapshot_root()
    if not root:
        return None
    guarded = GuardedSource(SnapshotSource(PITStore(Path(root))), AsOfGuard(day))
    try:
        df = guarded.daily_ohlcv(code, day, day)
    except SnapshotMissingError:
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    return float(df["close"].iloc[-1])


def overview_context(account_id: str) -> dict:
    """总览页上下文:折叠视图 + 持仓现价/浮盈 + 流水 + 表单预填。

    现价恒取快照**最新**交易日:持仓/现金折叠到当下,定价日若允许任选会出现
    "当下持仓 × 历史价"的混合口径,总资产不对应任何一个时点——故不提供 day 参数。
    """
    r = repo()
    baseline = r.latest_baseline(account_id)
    if baseline is None:
        return {"account_id": account_id, "opened": False,
                "default_cash": 200_000, "view": None, "rows": [],
                "fills": [], "totals": None, "price_day": None,
                "operation_id": uuid.uuid4().hex,
                "commission_bp": _COST.commission_bp, "stamp_bp": _COST.stamp_tax_bp}

    view = r.fold(account_id)
    price_day = market_service.pick_day(None)         # None = 无快照,现价栏诚实空
    baseline_codes = set(view.baseline_codes)

    rows = []
    mv_total, unreal_total = 0.0, 0.0
    priced_all, cost_known_all = True, True
    for p in view.positions:
        last = _close_at(p.code, price_day) if price_day else None
        if last is None:
            priced_all = False
            mv = unreal = None
        else:
            mv = round(last * p.qty, 2)
            mv_total += mv
            if p.qty <= 0 or p.code in baseline_codes:
                # 负持仓(超卖异常)与基线来源持仓(无成本价)成本口径无意义,
                # 浮盈诚实留空——fold 已为后者登记"勿据此算浮盈" anomaly
                unreal = None
                cost_known_all = False
            else:
                unreal = round(mv - p.cost_basis, 2)
                unreal_total += unreal
        rows.append({"code": p.code, "qty": p.qty, "avg_cost": p.avg_cost,
                     "cost_basis": p.cost_basis, "last": last, "mv": mv,
                     "unreal": unreal})

    unreal_complete = priced_all and cost_known_all
    equity = (round(view.cash + mv_total, 2)
              if (view.is_absolute_cash and priced_all) else None)
    totals = {"mv": round(mv_total, 2) if rows else 0.0,
              "unreal": round(unreal_total, 2), "unreal_complete": unreal_complete,
              "equity": equity, "priced_all": priced_all}

    fills = list(reversed(r.fills(account_id)))        # 最新在前
    return {"account_id": account_id, "opened": True, "view": view,
            "baseline": baseline, "rows": rows, "totals": totals,
            "fills": fills, "price_day": price_day.isoformat() if price_day else None,
            "trade_date_default": (price_day or Date.today()).isoformat(),
            "operation_id": uuid.uuid4().hex,          # 每次渲染新幂等键:防双击/刷新重提
            "commission_bp": _COST.commission_bp, "stamp_bp": _COST.stamp_tax_bp}
