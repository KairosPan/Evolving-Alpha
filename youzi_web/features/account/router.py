# youzi_web/features/account/router.py
"""账户页面 + 两个人工表单(开户 / 回报成交)。

钱路径纪律:开户与成交**只能人经表单/API 触发**,不经任何 agent 工具面;
web 层不做业务判断,领域错误(重复开户/幂等键冲突/参数错)翻成页内 flash
+ 相应状态码。表单 POST 拒绝跨站请求(Sec-Fetch-Site: cross-site)——
任意网页不得替人往账本里写钱;JSON API 侧由 CORS(未开放)天然挡住。
"""
from __future__ import annotations

import re
from datetime import date as Date

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from youzi.store.errors import DuplicateError
from youzi_web.features.account import service

router = APIRouter()

_CODE_RE = re.compile(r"^\d{6}$")


def _render(request: Request, account_id: str,
            flash: str | None = None, flash_kind: str = "ok", status: int = 200):
    ctx = service.overview_context(account_id)
    ctx.update({"request": request, "features": request.app.state.features,
                "active_feature_id": "account", "active_path": "/account/overview",
                "flash": flash, "flash_kind": flash_kind})
    return request.app.state.templates.TemplateResponse(
        request, "overview.html", ctx, status_code=status)


def _cross_site(request: Request) -> bool:
    """浏览器带 `Sec-Fetch-Site: cross-site` = 第三方网页发起的 POST → 拒。

    无该头(老浏览器/curl/测试)按本站放行——本地单人 co-pilot 的务实取舍。
    """
    return request.headers.get("sec-fetch-site", "").lower() == "cross-site"


@router.get("/account/overview")
def overview_page(request: Request, account_id: str = service.PAPER_ACCOUNT,
                  msg: str | None = None):
    return _render(request, account_id, flash=msg)


@router.post("/account/open")
def open_account_form(request: Request, account_id: str = Form(service.PAPER_ACCOUNT),
                      cash: float = Form(...)):
    if _cross_site(request):
        return _render(request, account_id, flash="已拒绝跨站请求:钱路径只接受本站表单",
                       flash_kind="err", status=403)
    try:
        service.repo().open_baseline(account_id=account_id, cash=cash)
    except DuplicateError as e:
        return _render(request, account_id, flash=str(e), flash_kind="err", status=409)
    except ValueError as e:
        return _render(request, account_id, flash=str(e), flash_kind="err", status=422)
    return RedirectResponse(
        f"/account/overview?account_id={account_id}&msg=模拟盘已开户", status_code=303)


@router.post("/account/fill")
def fill_form(request: Request, account_id: str = Form(...),
              operation_id: str = Form(...), trade_date: str = Form(...),
              code: str = Form(...), side: str = Form(...),
              price: float = Form(...), qty: int = Form(...),
              fee: float = Form(0.0)):
    if _cross_site(request):
        return _render(request, account_id, flash="已拒绝跨站请求:钱路径只接受本站表单",
                       flash_kind="err", status=403)
    code = code.strip()
    if side not in ("buy", "sell") or price <= 0 or qty <= 0 or fee < 0 \
            or not _CODE_RE.match(code):
        return _render(request, account_id,
                       flash="参数错误:code 为 6 位数字、side∈{buy,sell}、price/qty 为正、fee≥0",
                       flash_kind="err", status=422)
    try:
        day = Date.fromisoformat(trade_date)
    except ValueError:
        return _render(request, account_id, flash=f"交易日非法: {trade_date}",
                       flash_kind="err", status=422)
    r = service.repo()
    if r.latest_baseline(account_id) is None:
        return _render(request, account_id,
                       flash="账户未开户:请先开户(opening 基线),开户前入账的成交会被折叠排除",
                       flash_kind="err", status=409)
    try:
        _, created = r.record_fill(
            operation_id=operation_id, account_id=account_id, trade_date=day,
            code=code, side=side, price=price, qty=qty, fee=fee)
    except DuplicateError as e:            # 幂等键被复用提交了另一笔不同成交
        return _render(request, account_id, flash=str(e), flash_kind="err", status=409)
    msg = "成交已入账" if created else "重复提交:该笔已入账(幂等,未重复记账)"
    return RedirectResponse(
        f"/account/overview?account_id={account_id}&msg={msg}", status_code=303)
