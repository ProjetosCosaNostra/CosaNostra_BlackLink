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
from app.database import engine, ensure_sqlite_schema

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
# ROUTERS (IMPORT SEGURO — NÃO DEPENDE DO __init__.py)
# ==================================================
import app.routers.auth as auth
import app.routers.product as product
import app.routers.blacklinks as blacklinks
import app.routers.catalog as catalog
import app.routers.admin as admin
import app.routers.panel as panel
import app.routers.payment as payment
import app.routers.plan as plan
import app.routers.webhook as webhook

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

# Webhook router já tem prefix="/webhook" dentro dele.
# Aqui NÃO coloca prefix, pra não virar /webhook/webhook/...
app.include_router(webhook.router, tags=["Webhook"])

# ==================================================
# STARTUP
# ==================================================
@app.on_event("startup")
def on_startup():
    logger.info("🚀 Iniciando CosaNostra BlackLink")
    ensure_sqlite_schema(engine)
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
