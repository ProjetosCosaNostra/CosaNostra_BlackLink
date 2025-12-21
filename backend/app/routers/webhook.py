from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

from app.services.plan_catalog import (
    normalize_plan,
    get_plan,
    calc_plan_expiry,
    PLAN_FREE,
)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# ============================================================
# 🔐 FUTURO: validação de assinatura Mercado Pago
# ============================================================
def verify_signature(headers: Dict[str, str], body: Dict[str, Any]) -> bool:
    """
    Placeholder para validação real:
    - x-signature
    - x-request-id
    - secret
    """
    return True  # por enquanto aceitamos tudo


# ============================================================
# 🔧 Aplicar plano após pagamento aprovado
# ============================================================
def apply_paid_plan(
    *,
    user: models.BlackLinkUser,
    plan_id: str,
    months: int,
) -> None:
    plan = get_plan(plan_id)

    if not plan.is_sellable:
        raise HTTPException(status_code=400, detail="Plano não vendável")

    now = datetime.now(timezone.utc)

    # Renovação: soma se ainda ativo
    if (
        user.plan in ("pro", "don")
        and user.plan_status == "active"
        and user.plan_expires_at
        and user.plan_expires_at > now
    ):
        start_at = user.plan_expires_at
    else:
        start_at = now

    expires_at = calc_plan_expiry(start_at, months, plan.id)

    # Histórico
    if user.plan in ("pro", "don"):
        user.last_paid_plan = user.plan
        user.last_paid_expires_at = user.plan_expires_at

    user.plan = plan.id
    user.plan_status = "active"
    user.plan_started_at = start_at
    user.plan_expires_at = expires_at


# ============================================================
# 📩 WEBHOOK MERCADO PAGO
# ============================================================
@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Estrutura REAL de webhook Mercado Pago.

    Espera payload parecido com:
    {
      "type": "payment",
      "data": {
        "id": "1234567890"
      }
    }

    Em produção:
    - buscar pagamento via API MP
    - validar status = approved
    """

    payload = await request.json()

    # --- segurança futura
    if not verify_signature(dict(request.headers), payload):
        raise HTTPException(status_code=401, detail="Assinatura inválida")

    event_type = payload.get("type")
    data = payload.get("data") or {}

    if event_type != "payment":
        return {"status": "ignored", "reason": "Evento não é pagamento"}

    payment_id = data.get("id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment.id ausente")

    # ========================================================
    # 🔥 MOCK DE CONSULTA AO MERCADO PAGO
    # ========================================================
    # Aqui futuramente:
    # payment = mp.payment().get(payment_id)

    payment_status = "approved"  # fake controlado
    metadata = {
        "username": payload.get("username"),
        "plan": payload.get("plan"),
        "months": payload.get("months", 1),
        "email": payload.get("email"),
    }

    if payment_status != "approved":
        return {"status": "ignored", "reason": "Pagamento não aprovado"}

    username = metadata.get("username")
    plan_id = normalize_plan(metadata.get("plan"))
    months = int(metadata.get("months") or 1)

    if not username or plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Dados de pagamento inválidos")

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    apply_paid_plan(
        user=user,
        plan_id=plan_id,
        months=months,
    )

    if metadata.get("email"):
        user.email = metadata["email"]

    db.add(user)
    db.commit()

    return {
        "status": "processed",
        "username": user.username,
        "plan": user.plan,
        "expires_at": user.plan_expires_at,
    }
