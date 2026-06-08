# youzi_web/app.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

WEB_DIR = Path(__file__).resolve().parent
APP_TEMPLATES = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
FEATURES_DIR = WEB_DIR / "features"


def _make_templates() -> Jinja2Templates:
    dirs = [APP_TEMPLATES] + [p for p in FEATURES_DIR.glob("*/templates") if p.is_dir()]
    env = Environment(loader=ChoiceLoader([FileSystemLoader(str(d)) for d in dirs]),
                      autoescape=select_autoescape())
    return Jinja2Templates(env=env)


def create_app() -> FastAPI:
    from youzi_web.features import FEATURES
    app = FastAPI(title="youzi")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = _make_templates()
    app.state.features = FEATURES
    for f in FEATURES:
        app.include_router(f.router)

    @app.get("/")
    def home(request: Request):
        if FEATURES and FEATURES[0].subnav:
            return RedirectResponse(FEATURES[0].subnav[0].path)
        # 空注册表:渲染外壳 landing
        return app.state.templates.TemplateResponse(
            request,
            "base.html",
            {"request": request, "features": FEATURES,
             "active_feature_id": None, "active_path": None})

    return app


app = create_app()          # uvicorn youzi_web.app:app
