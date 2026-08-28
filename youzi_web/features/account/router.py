# youzi_web/features/account/router.py
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/account/overview")
def overview_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request, "overview.html",
        {"request": request, "features": request.app.state.features,
         "active_feature_id": "account", "active_path": "/account/overview"})
