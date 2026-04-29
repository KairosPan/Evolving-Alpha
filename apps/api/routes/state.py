"""GET /api/state/{tid} — current checkpoint snapshot."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
