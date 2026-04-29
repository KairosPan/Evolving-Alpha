"""GET /api/state/{tid} — current checkpoint snapshot.

POST /api/state/{tid}/edit — apply a whitelisted patch and start a new run.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")


@router.get("/state/{tid}")
def get_state(tid: str, request: Request) -> dict:
    rt = request.app.state.runtime
    cfg = {"configurable": {"thread_id": tid}}
    snapshot = rt._graph.get_state(cfg)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="no state for thread_id")
    from apps.api.graph_runtime import _jsonable
    return _jsonable(snapshot.values)


class EditBody(BaseModel):
    path: str
    value: object


@router.post("/state/{tid}/edit")
async def post_edit(tid: str, body: EditBody, request: Request) -> dict:
    rt = request.app.state.runtime
    if not rt.has_state(tid):
        raise HTTPException(404, f"no state for {tid}")
    try:
        new_tid = await rt.edit(tid, body.path, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "rerun_tid": new_tid}
