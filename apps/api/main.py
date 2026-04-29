"""FastAPI entry — wraps youzi_agent graph runtime."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="youzi-agent web API", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
