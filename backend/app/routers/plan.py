from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BlackLinkUser
from app.schemas import UserOut

router = APIRouter(
    prefix="/plan",
    tags=["Plan"],
)

# ============================================================
# CONFIGURAÇÃO DE PLANOS (FONTE ÚNICA DE VERDADE)
# ============================================================
PLANS = {
    "free": {
        "label": "FREE",
        "product_limit": 3,
        "sellable": False,
    },
    "pro": {
        "label": "PRO",
        "product_limit": 20,
        "sellable": True,
    },
    "don": {
        "label": "DON",
        "product_limit": None,  # ilimitado
        "sellable": True,
    },
}


def _normalize_plan(plan: str) -> str:
    return plan.strip().lower()


def _validate_plan(plan: str) -> None:
    if plan not in PLANS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_plan",
                "message": f"Plano inválido. Use: {', '.join(PLANS.keys())}",
            },
        )


# ============================================================
# GET /plan/{username}
# Retorna status atual do plano
# ============================================================
@router.get("/{username}")
def get_user_plan(
    username: str,
    db: Session = Depends(get_db),
):
    user = (
        db.query(BlackLinkUser)
        .filter(BlackLinkUser.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "username": user.username,
        "plan": user.plan,
        "plan_status": user.plan_status,
        "plan_started_at": user.plan_started_at,
        "plan_expires_at": user.plan_expires_at,
        "product_limit": PLANS.get(user.plan, PLANS["free"])["product_limit"],
    }


# ============================================================
# POST /plan/upgrade/{username}
# Upgrade manual (FREE → PRO → DON)
# ============================================================
@router.post("/upgrade/{username}", response_model=UserOut)
def upgrade_plan(
    username: str,
    plan: str = Query(..., description="Plano desejado: pro | don"),
    months: Optional[int] = Query(1, ge=1, le=36),
    db: Session = Depends(get_db),
):
    plan = _normalize_plan(plan)
    _validate_plan(plan)

    if not PLANS[plan]["sellable"]:
        raise HTTPException(
            status_code=400,
            detail="Plano FREE não pode ser adquirido via upgrade",
        )

    user = (
        db.query(BlackLinkUser)
        .filter(BlackLinkUser.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔒 Regras de negócio
    if user.plan == "don":
        raise HTTPException(
            status_code=403,
            detail="Usuário já está no plano DON (máximo)",
        )

    if user.plan == plan:
        raise HTTPException(
            status_code=400,
            detail=f"Usuário já está no plano {plan.upper()}",
        )

    now = datetime.now(timezone.utc)

    # ========================================================
    # APLICA UPGRADE
    # ========================================================
    user.last_paid_plan = user.plan
    user.last_paid_expires_at = user.plan_expires_at

    user.plan = plan
    user.plan_status = "active"
    user.plan_started_at = now
    user.plan_expires_at = None  # pode ser controlado depois por pagamento real

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
