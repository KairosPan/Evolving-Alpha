# youzi_web/features/research/router.py
from fastapi import APIRouter, Request

from youzi_web.features.research.service import get_seed_harness_view

router = APIRouter()


@router.get("/research/harness")
def harness_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "harness.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "research", "active_path": "/research/harness",
         "h": get_seed_harness_view()})
