from __future__ import annotations

from fastapi import HTTPException
from app.config import PLAN_LIMITS


def get_plan_limits(plan: str | None) -> dict:
    """
    Retorna a configuração do plano.
    Se vier algo inválido, assume FREE.
    """
    p = (plan or "free").lower().strip()
    return PLAN_LIMITS.get(p, PLAN_LIMITS["free"])


def check_product_limit(plan: str | None, total_products: int) -> None:
    """
    Enforce: limite de produtos por plano.
    FREE: 3
    PRO: 20
    DON: ilimitado
    """
    limits = get_plan_limits(plan)
    max_products = limits.get("max_products", 3)

    if max_products is None:
        return  # ilimitado

    if total_products >= max_products:
        raise HTTPException(
            status_code=403,
            detail=f"Limite atingido: plano {str(plan or 'free').upper()} permite até {max_products} produtos."
        )


def require_auto_ingest(plan: str | None) -> None:
    """
    Enforce: ingestão automática somente PRO/DON.
    """
    limits = get_plan_limits(plan)
    if not limits.get("auto_ingest", False):
        raise HTTPException(
            status_code=403,
            detail="Ingestão automática disponível apenas para planos PRO ou DON."
        )


def require_featured_allowed(plan: str | None) -> None:
    """
    Enforce: destaque (featured) somente PRO/DON.
    """
    limits = get_plan_limits(plan)
    if not limits.get("featured_allowed", False):
        raise HTTPException(
            status_code=403,
            detail="Destaque disponível apenas para planos PRO ou DON."
        )
