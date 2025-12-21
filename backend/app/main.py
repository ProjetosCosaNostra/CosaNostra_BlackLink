from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# ==================================================
# LOG
# ==================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("blacklink")

# ==================================================
# PATHS
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ==================================================
# DATABASE
# ==================================================
from app.database import ensure_sqlite_schema

# ==================================================
# SETTINGS
# ==================================================
from app.config import settings

# ==================================================
# FASTAPI APP
# ==================================================
app = FastAPI(
    title="CosaNostra BlackLink",
    version="5.2",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url=None,
)

# ==================================================
# MIDDLEWARE
# ==================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# ROUTERS (IMPORTAÇÃO EXPLÍCITA)
# ==================================================
from app.routers import (
    auth,
    product,
    blacklinks,
    catalog,
    admin,
    panel,
    payment,
    plan,
    webhook,
)

# ==================================================
# ROUTERS (REGISTRO)
# ==================================================
app.include_router(auth.router, tags=["Auth"])
app.include_router(product.router, tags=["Product"])
app.include_router(blacklinks.router, tags=["BlackLink"])
app.include_router(catalog.router, tags=["Catalog"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(panel.router, tags=["Panel"])
app.include_router(payment.router, tags=["Payment"])
app.include_router(plan.router, tags=["Plan"])

# ✅ IMPORTANTE:
# O router do webhook JÁ tem prefix="/webhook" dentro do arquivo webhook.py
# então aqui NÃO coloque prefix novamente.
app.include_router(webhook.router, tags=["Webhook"])

# ==================================================
# STARTUP
# ==================================================
@app.on_event("startup")
def on_startup():
    logger.info("🚀 Iniciando CosaNostra BlackLink")
    ensure_sqlite_schema()
    logger.info("✅ Banco de dados pronto")

# ==================================================
# HEALTHCHECK
# ==================================================
@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "service": "blacklink"}

# ==================================================
# FRONTEND TEMPLATE (OPCIONAL)
# ==================================================
@app.get("/ui", response_class=HTMLResponse)
def ui_home(request: Request):
    return templates.TemplateResponse(
        "user_page.html",
        {"request": request},
    )
