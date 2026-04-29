"""History — read runs/YYYY-MM-DD/{report.json,state_snapshot.json}."""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api")


def _runs_dir(request: Request) -> Path:
    return Path(request.app.state.runs_dir)


@router.get("/runs")
def list_runs(request: Request, limit: int = Query(60, gt=0, le=365)) -> list[dict]:
    root = _runs_dir(request)
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        rep = d / "report.json"
        if not rep.exists():
            continue
        try:
            data = json.loads(rep.read_text())
        except Exception:
            continue
        out.append({
            "date": d.name,
            "candidates_count": len(data.get("candidates", []) or []),
            "errors_count": len(data.get("errors", []) or []),
            "has_plan": data.get("plan") is not None,
        })
        if len(out) >= limit:
            break
    return out


@router.get("/runs/{date}")
def get_run(date: str, request: Request) -> dict:
    snap = _runs_dir(request) / date / "state_snapshot.json"
    if not snap.exists():
        raise HTTPException(status_code=404, detail=f"no snapshot for {date}")
    return json.loads(snap.read_text())
