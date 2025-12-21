import httpx
import time
from sqlalchemy.orm import Session
from typing import List

from app.database import SessionLocal
from app import models
from app.config import PLAN_LIMITS


# ============================================================
# 🔁 LINK GUARDIAN
# Serviço autônomo de validação de links afiliados
# Enforce PASSO 2: somente PRO/DON
# ============================================================

CHECK_INTERVAL_SECONDS = 60 * 30  # 30 minutos


def _is_link_alive(url: str) -> bool:
    if not url:
        return False

    if "mercadolivre.com" not in url:
        return True

    try:
        with httpx.Client(follow_redirects=True, timeout=5.0) as client:
            resp = client.head(url)
            if resp.status_code == 405:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})

        if resp.status_code in (404, 410):
            return False

        return True

    except httpx.RequestError:
        return True


def _guardian_enabled_for_plan(plan: str | None) -> bool:
    p = (plan or "free").lower().strip()
    return PLAN_LIMITS.get(p, PLAN_LIMITS["free"]).get("link_guardian", False)


def run_link_guardian():
    """
    Loop infinito de verificação automática.
    Roda enquanto o backend estiver ligado.
    """

    print("🛡️ Link Guardian iniciado.")

    while True:
        db: Session = SessionLocal()
        try:
            products: List[models.BlackLinkProduct] = (
                db.query(models.BlackLinkProduct)
                .filter(models.BlackLinkProduct.is_active == 1)
                .all()
            )

            for product in products:
                # 🔒 Enforce PASSO 2: Guardian só atua em PRO/DON
                user = (
                    db.query(models.BlackLinkUser)
                    .filter(models.BlackLinkUser.id == product.owner_id)
                    .first()
                )

                if not user:
                    continue

                if not _guardian_enabled_for_plan(user.plan):
                    continue

                alive = _is_link_alive(product.url)

                if not alive:
                    product.is_active = 0
                    product.is_featured = 0
                    db.add(product)
                    print(f"❌ Produto desativado automaticamente: {product.title}")

            db.commit()

        except Exception as e:
            print("⚠️ Erro no Link Guardian:", e)

        finally:
            db.close()

        time.sleep(CHECK_INTERVAL_SECONDS)
