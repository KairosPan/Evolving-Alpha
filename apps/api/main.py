"""FastAPI entry — wraps youzi_agent graph runtime."""
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .graph_runtime import GraphRuntime
from .routes import run as run_routes


def build_app(checkpoint_path: str | None = None,
              runs_dir: str | None = None,
              cache_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="youzi-agent web API", version="0.1.0")
    # dev CORS — Next dev server on :3000
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    from .routes import state as state_routes, runs as runs_routes, kline as kline_routes
    app.include_router(run_routes.router)
    app.include_router(state_routes.router)
    app.include_router(runs_routes.router)
    app.include_router(kline_routes.router)

    app.state.runtime = GraphRuntime(
        checkpoint_path=checkpoint_path or os.environ.get("YOUZI_CHECKPOINT", "checkpoints.db")
    )
    app.state.runs_dir = runs_dir or os.environ.get("YOUZI_RUNS_DIR", "runs")
    app.state.cache_dir = cache_dir or os.environ.get("YOUZI_CACHE_DIR", "data_cache")
    return app


app = build_app()
