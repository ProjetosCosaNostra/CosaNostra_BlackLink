from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


# ==================================================
# BASE DIR
# ==================================================
BASE_DIR = Path(__file__).resolve().parent

# ==================================================
# TEMPLATES
# ==================================================
TEMPLATES_DIR = BASE_DIR / "templates"

# ==================================================
# PLANOS / LIMITES SAAS (LEGADO)
# ==================================================
PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_products": 3,
        "auto_ingest": False,
        "link_guardian": False,
        "featured_allowed": False,
    },
    "pro": {
        "max_products": 20,
        "auto_ingest": True,
        "link_guardian": True,
        "featured_allowed": True,
    },
    "don": {
        "max_products": None,
        "auto_ingest": True,
        "link_guardian": True,
        "featured_allowed": True,
    },
}


# ==================================================
# UTIL — montar URLs públicas corretamente
# ==================================================
def _join_url(base: str, path: str) -> str:
    base = (base or "").strip()
    path = (path or "").strip()

    if not base:
        base = "http://localhost"

    if not base.startswith(("http://", "https://")):
        base = "http://" + base

    if not path.startswith("/"):
        path = "/" + path

    return base.rstrip("/") + path


# ==================================================
# SETTINGS
# ==================================================
class Settings(BaseSettings):
    """
    Config central do BlackLink.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --------------------------------------------------
    # APP / AMBIENTE
    # --------------------------------------------------
    ENV: str = "dev"  # dev | prod
    APP_BASE_URL: str = "http://localhost"

    # --------------------------------------------------
    # DATABASE
    # --------------------------------------------------
    DATABASE_URL: str = "sqlite:///./blacklink.db"

    # --------------------------------------------------
    # MERCADO PAGO — AMBIENTE
    # --------------------------------------------------
    MP_ENV: str = "test"  # test | production

    # --------------------------------------------------
    # MERCADO PAGO — CREDENCIAIS
    # --------------------------------------------------
    MP_ACCESS_TOKEN: Optional[str] = None
    MP_PUBLIC_KEY: Optional[str] = None
    MP_WEBHOOK_SECRET: Optional[str] = None

    # --------------------------------------------------
    # MERCADO PAGO — PATHS INTERNOS
    # --------------------------------------------------
    MP_WEBHOOK_PATH: str = "/webhook/mercadopago"
    MP_SUCCESS_PATH: str = "/payment/success"
    MP_FAILURE_PATH: str = "/payment/failure"
    MP_PENDING_PATH: str = "/payment/pending"

    # --------------------------------------------------
    # MERCADO PAGO — URLs FINAIS (geradas)
    # --------------------------------------------------
    MP_WEBHOOK_URL: Optional[str] = None
    MP_SUCCESS_URL: Optional[str] = None
    MP_FAILURE_URL: Optional[str] = None
    MP_PENDING_URL: Optional[str] = None

    # --------------------------------------------------
    # POST INIT — GARANTIA ABSOLUTA
    # --------------------------------------------------
    def model_post_init(self, __context: Any) -> None:
        self.MP_WEBHOOK_URL = (
            self.MP_WEBHOOK_URL
            or _join_url(self.APP_BASE_URL, self.MP_WEBHOOK_PATH)
        )

        self.MP_SUCCESS_URL = (
            self.MP_SUCCESS_URL
            or _join_url(self.APP_BASE_URL, self.MP_SUCCESS_PATH)
        )

        self.MP_FAILURE_URL = (
            self.MP_FAILURE_URL
            or _join_url(self.APP_BASE_URL, self.MP_FAILURE_PATH)
        )

        self.MP_PENDING_URL = (
            self.MP_PENDING_URL
            or _join_url(self.APP_BASE_URL, self.MP_PENDING_PATH)
        )

        # 🔥 HARD FAIL EM PRODUÇÃO
        if self.ENV == "prod":
            if not self.MP_ACCESS_TOKEN:
                raise RuntimeError("MP_ACCESS_TOKEN é obrigatório em produção")
            if self.MP_ENV != "production":
                raise RuntimeError("MP_ENV deve ser 'production' em produção")


# ==================================================
# INSTANCE GLOBAL
# ==================================================
settings = Settings()
