from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.config import settings
from app.schemas import PaymentProcessRequest, PaymentProcessResponse
from app.services.plan_catalog import (
    get_plan,
    normalize_plan,
    calc_plan_expiry,
    PLAN_FREE,
)

# ============================================================
# ROUTER
# ============================================================
router = APIRouter(prefix="/payment", tags=["Payment"])


# ============================================================
# UTIL — aplicar upgrade real de plano
# ============================================================
def apply_plan_upgrade(
    *,
    user: models.BlackLinkUser,
    plan_id: str,
    months: int,
) -> models.BlackLinkUser:
    """
    Aplica upgrade real de plano no usuário.

    Regras:
    - FREE não é vendável
    - PRO / DON ativam plano com datas
    - Renovação soma tempo se ainda ativo
    """

    plan = get_plan(plan_id)

    if not plan.is_sellable:
        raise HTTPException(status_code=400, detail="Plano não vendável")

    now = datetime.now(timezone.utc)

    # Renovação inteligente
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

    # Aplica plano
    user.plan = plan.id
    user.plan_status = "active"
    user.plan_started_at = start_at
    user.plan_expires_at = expires_at

    return user


# ============================================================
# ENDPOINT 1 — CHECKOUT (Mercado Pago Preference)
# ============================================================
@router.post("/checkout")
def create_checkout_preference(
    payload: PaymentProcessRequest,
    db: Session = Depends(get_db),
):
    """
    Cria uma PREFERENCE do Mercado Pago.
    Roda em SANDBOX ou PRODUÇÃO dependendo do token.

    IMPORTANTE:
    - external_reference precisa ser consistente com o webhook:
        username:plan:months
    - notification_url aponta para /webhook/mercadopago (settings.MP_WEBHOOK_URL)
    """

    username = (payload.username or "").strip().lower()
    plan_id = normalize_plan(payload.plan)
    months = payload.months or 1

    if not username:
        raise HTTPException(status_code=400, detail="username é obrigatório")

    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="months inválido (1..24)")

    if plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Plano FREE não é vendável")

    plan = get_plan(plan_id)

    if not plan.is_sellable:
        raise HTTPException(status_code=400, detail="Plano inválido")

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if not settings.MP_ACCESS_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Mercado Pago não configurado (MP_ACCESS_TOKEN ausente)",
        )

    if not settings.MP_WEBHOOK_URL:
        raise HTTPException(
            status_code=500,
            detail="MP_WEBHOOK_URL ausente (notification_url do Mercado Pago)",
        )

    import mercadopago

    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    unit_price = (plan.price_brl_cents / 100) * months

    preference_data = {
        "items": [
            {
                "title": f"Plano {plan.name} — {months} mês(es)",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(unit_price),
            }
        ],
        "payer": {
            "email": payload.email or user.email or "cliente@blacklink.app"
        },
        # ✅ webhook parseia "username:plan:months"
        "external_reference": f"{user.username}:{plan.id}:{months}",
        "notification_url": settings.MP_WEBHOOK_URL,
        "back_urls": {
            "success": settings.MP_SUCCESS_URL,
            "failure": settings.MP_FAILURE_URL,
            "pending": settings.MP_PENDING_URL,
        },
        "auto_return": "approved",
    }

    preference = sdk.preference().create(preference_data)

    if preference.get("status") not in (200, 201):
        raise HTTPException(
            status_code=500,
            detail="Erro ao criar preference no Mercado Pago",
        )

    pref = preference["response"]

    return {
        "preference_id": pref["id"],
        "init_point": pref.get("init_point"),
        "sandbox_init_point": pref.get("sandbox_init_point"),
        # útil para debug:
        "external_reference": preference_data["external_reference"],
        "notification_url": preference_data["notification_url"],
    }


# ============================================================
# ENDPOINT 2 — PROCESSAMENTO (PRODUÇÃO-SAFE) — FALLBACK/ADMIN
# ============================================================
@router.post("/process", response_model=PaymentProcessResponse)
def process_payment(
    payload: PaymentProcessRequest,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    """
    Processa pagamento aprovado.

    Uso recomendado:
    - Fallback/admin ou processamento manual controlado.

    Em PRODUÇÃO:
    - Exige payment_id
    - Valida pagamento no Mercado Pago
    - Confere status = approved
    - Confere external_reference
    - Impede ativação manual/fake
    """

    username = (payload.username or "").strip().lower()
    plan_id = normalize_plan(payload.plan)
    months = payload.months or 1

    if not username:
        raise HTTPException(status_code=400, detail="username é obrigatório")

    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="months inválido (1..24)")

    if plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Plano FREE não é vendável")

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    plan = get_plan(plan_id)

    if not plan.is_sellable:
        raise HTTPException(status_code=400, detail="Plano inválido")

    # ========================================================
    # PRODUÇÃO — valida pagamento real
    # ========================================================
    if settings.MP_ENV == "production":
        if not payload.payment_id:
            raise HTTPException(
                status_code=400,
                detail="payment_id é obrigatório em produção",
            )

        # Header de segurança opcional
        if settings.MP_WEBHOOK_SECRET:
            if x_webhook_secret != settings.MP_WEBHOOK_SECRET:
                raise HTTPException(
                    status_code=403,
                    detail="Webhook não autorizado",
                )

        import mercadopago

        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
        payment = sdk.payment().get(payload.payment_id)

        if payment.get("status") != 200:
            raise HTTPException(400, "Pagamento não encontrado no Mercado Pago")

        payment_data = payment["response"]

        if payment_data.get("status") != "approved":
            raise HTTPException(400, "Pagamento não aprovado")

        expected_ref = f"{user.username}:{plan.id}:{months}"
        if payment_data.get("external_reference") != expected_ref:
            raise HTTPException(
                400,
                "Referência de pagamento inválida",
            )

    # ========================================================
    # APLICA PLANO (pagamento aprovado)
    # ========================================================
    user = apply_plan_upgrade(
        user=user,
        plan_id=plan.id,
        months=months,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return PaymentProcessResponse(
        status="approved",
        message="Plano ativado com sucesso",
        username=user.username,
        plan=user.plan,
        plan_status=user.plan_status,
        plan_expires_at=user.plan_expires_at,
    )
