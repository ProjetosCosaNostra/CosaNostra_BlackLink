from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserOut

router = APIRouter(
    prefix="/plan",
    tags=["Plan"]
)

# ============================================================
# CONFIGURAÇÃO DE PLANOS
# ============================================================
VALID_PLANS = {
    "pro": {
        "label": "PRO",
        "product_limit": 20,
    },
    "don": {
        "label": "DON",
        "product_limit": None,  # ilimitado
    }
}


# ============================================================
# POST /plan/upgrade/{username}
# Upgrade de plano (FREE → PRO → DON)
# ============================================================
@router.post("/upgrade/{username}", response_model=UserOut)
def upgrade_plan(
    username: str,
    plan: str = Query(..., description="Plano desejado: pro | don"),
    db: Session = Depends(get_db),
):
    plan = plan.lower()

    # 🔎 Validação do plano
    if plan not in VALID_PLANS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_plan",
                "message": f"Plano inválido. Use: {', '.join(VALID_PLANS.keys())}"
            }
        )

    # 🔎 Busca usuário
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # 🔒 Bloqueio de downgrade
    if user.plan == "don":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "upgrade_not_allowed",
                "message": "Usuário já está no plano DON (máximo)."
            }
        )

    # 🔒 Impede PRO → PRO
    if user.plan == plan:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "already_on_plan",
                "message": f"Usuário já está no plano {plan.upper()}."
            }
        )

    # ========================================================
    # APLICA UPGRADE
    # ========================================================
    now = datetime.utcnow()

    user.plan = plan
    user.plan_status = "active"
    user.plan_started_at = now
    user.plan_expires_at = None  # pode ser controlado depois por pagamento
    user.last_paid_plan = plan
    user.last_paid_expires_at = None

    db.commit()
    db.refresh(user)

    return user
