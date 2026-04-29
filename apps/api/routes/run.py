"""Run lifecycle: POST /run, GET /run/{tid}/stream, POST /run/{tid}/{resume,abort}."""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api")


class StartRunBody(BaseModel):
    date: str
    use_llm: bool = True
    refresh: bool = False


@router.post("/run")
async def post_run(body: StartRunBody, request: Request) -> dict:
    rt = request.app.state.runtime
    tid = await rt.start(date=body.date, use_llm=body.use_llm, refresh=body.refresh)
    return {"thread_id": tid}


@router.get("/run/{tid}/stream")
async def get_stream(tid: str, request: Request):
    rt = request.app.state.runtime
    if tid not in rt._queues:
        raise HTTPException(status_code=404, detail="unknown thread_id")

    last_id = int(request.headers.get("last-event-id", "0") or 0)

    async def gen():
        async for n, ev in rt.stream(tid, last_id=last_id):
            yield {"id": str(n), "event": ev["type"], "data": json.dumps(ev, default=str)}

    return EventSourceResponse(gen())


class ResumeBody(BaseModel):
    node: str | None = None
    action: str = "approve"
    patch: dict | None = None


@router.post("/run/{tid}/resume")
async def post_resume(tid: str, body: ResumeBody, request: Request) -> dict:
    rt = request.app.state.runtime
    await rt.resume(tid, {"action": body.action, "patch": body.patch or {}})
    return {"ok": True}


@router.post("/run/{tid}/abort")
async def post_abort(tid: str, request: Request) -> dict:
    rt = request.app.state.runtime
    try:
        await rt.resume(tid, {"action": "abort", "patch": {}})
    except RuntimeError:
        pass  # nothing pending — silently ok
    return {"ok": True}
