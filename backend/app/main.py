from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from threading import Thread
from pathlib import Path
import logging

# ==================================================
# LOG
# ==================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("blacklink")

# ==================================================
# PATHS ABSOLUTOS
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

# ==================================================
# DATABASE
# ==================================================
from app.database import Base, engine, ensure_sqlite_schema

# ==================================================
# SETTINGS
# ==================================================
from app.config import settings

# ==================================================
# ROUTERS
# ==================================================
from app.routers import (
    auth,
    product,
    blacklinks,
    catalog,
    admin,
    panel,
    payment,
)

# ==================================================
# SERVICES
# ==================================================
from app.services.link_guardian import run_link_guardian

# ==================================================
# DB INIT
# (create_all não cria colunas novas; ensure_sqlite_schema adiciona colunas faltantes)
# IMPORTANTE: PASSO 3 adiciona colunas de ciclo de vida (plan_status, expires_at etc.)
# ==================================================
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema(engine)

# ==================================================
# APP
# ==================================================
app = FastAPI(
    title="CosaNostra BlackLink",
    version="5.2",  # PASSO 3
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ==================================================
# CORS
# ==================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================
# HEALTH
# ==================================================
@app.get("/")
def health():
    return {"status": "ok", "service": "blacklink"}

# ==================================================
# CHECKOUT
# ==================================================
@app.get("/checkout", response_class=HTMLResponse)
def checkout(request: Request):
    logger.info(f"Renderizando checkout em: {TEMPLATES_DIR}")
    return templates.TemplateResponse(
        "payment.html",
        {
            "request": request,
            "public_key": settings.MP_PUBLIC_KEY,
        }
    )

# ==================================================
# ROUTERS
# IMPORTANTE:
# - auth.router já tem prefix="/auth"
# - admin.router já tem prefix="/admin"
# - product.router deve ter prefix="/product"
# - panel.router já trabalha com /painel...
# - payment.router tem prefix="/payment"
# ==================================================
app.include_router(auth.router)
app.include_router(product.router)
app.include_router(blacklinks.router)
app.include_router(catalog.router)
app.include_router(admin.router)
app.include_router(panel.router)
app.include_router(payment.router)

# ==================================================
# STARTUP
# ==================================================
@app.on_event("startup")
def startup():
    try:
        thread = Thread(target=run_link_guardian, daemon=True)
        thread.start()
        logger.info("Link Guardian iniciado")
    except Exception as e:
        logger.error(f"Guardian falhou: {e}")
