# youzi_web/features/strategy/router.py — 策略模块(吸收研究/决策路由,三大件 IA 的核心件)
from __future__ import annotations

from fastapi import APIRouter, Request

from youzi_mcp import harness_core as core
from youzi_web.data_access import seed_harness
from youzi_web.features.decision.router import router as decision_router
from youzi_web.features.research.router import router as research_router
from youzi_web.features.strategy import service

router = APIRouter()
router.include_router(research_router)   # /research/*(对比/精炼/轨迹/旧 harness 页)
router.include_router(decision_router)   # /decision/cockpit


# ── JSON API ──────────────────────────────────────────────────────────────

@router.get("/api/strategy/skills")
def api_skills(phase: str | None = None, status: str | None = None):
    return {"skills": core.skills_view(seed_harness(), phase=phase, status=status)}


@router.get("/api/strategy/lens")
def api_lens(phase: str):
    return core.lens_view(seed_harness(), phase)


@router.get("/api/strategy/doctrine")
def api_doctrine():
    return core.doctrine_view(seed_harness())


@router.get("/api/strategy/memory")
def api_memory():
    return {"lessons": core.memory_view(seed_harness())}


@router.get("/api/strategy/cycle")
def api_cycle():
    return {"phases": core.cycle_view(seed_harness())}


# ── 页面 ─────────────────────────────────────────────────────────────────

def _shell(request: Request, path: str, extra: dict) -> dict:
    return {"request": request, "features": request.app.state.features,
            "active_feature_id": "strategy", "active_path": path, **extra}


@router.get("/strategy/skills")
def skills_page(request: Request, phase: str | None = None, status: str | None = None):
    return request.app.state.templates.TemplateResponse(
        request, "skills.html",
        _shell(request, "/strategy/skills", service.skills_context(phase, status)))


@router.get("/strategy/doctrine")
def doctrine_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "doctrine.html",
        _shell(request, "/strategy/doctrine", service.doctrine_context()))


@router.get("/strategy/cycle")
def cycle_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "cycle.html",
        _shell(request, "/strategy/cycle", {"ring": service.cycle_ring()}))
