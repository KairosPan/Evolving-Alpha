"""Run lifecycle: POST /run, GET /run/{tid}/stream."""
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

    async def gen():
        async for ev in rt.stream(tid):
            yield {"event": ev["type"], "data": json.dumps(ev, default=str)}

    return EventSourceResponse(gen())
