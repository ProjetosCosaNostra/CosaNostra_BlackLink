from __future__ import annotations

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.config import settings

from app.services.plan_catalog import (
    normalize_plan,
    get_plan,
    calc_plan_expiry,
    PLAN_FREE,
)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# ============================================================
# 🔐 Segurança opcional (recomendado)
# ============================================================
def _verify_webhook_secret(x_webhook_secret: Optional[str]) -> None:
    """
    Se settings.MP_WEBHOOK_SECRET estiver definido, exige header:
    X-Webhook-Secret: <segredo>
    """
    if getattr(settings, "MP_WEBHOOK_SECRET", None):
        if not x_webhook_secret or x_webhook_secret != settings.MP_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Webhook não autorizado")


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
# 🧩 Helpers
# ============================================================
def _extract_payment_id(payload: Dict[str, Any]) -> Optional[str]:
    data = payload.get("data") or {}
    pid = data.get("id") or payload.get("id") or payload.get("data_id")
    if pid:
        return str(pid)

    resource = payload.get("resource")
    if isinstance(resource, str) and resource.strip():
        try:
            return resource.rstrip("/").split("/")[-1]
        except Exception:
            return None

    return None


def _parse_external_reference(external_reference: str) -> Tuple[str, str, int]:
    """
    Esperado: username:plan:months
    """
    if not external_reference or ":" not in external_reference:
        raise HTTPException(status_code=400, detail="external_reference inválido")

    parts = external_reference.split(":")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="external_reference inválido")

    username = parts[0].strip()
    plan_id = normalize_plan(parts[1].strip())

    try:
        months = int(parts[2])
    except Exception:
        raise HTTPException(status_code=400, detail="months inválido no external_reference")

    if not username:
        raise HTTPException(status_code=400, detail="username inválido no external_reference")
    if plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Plano FREE não é vendável")
    if months < 1:
        raise HTTPException(status_code=400, detail="months inválido")

    return username, plan_id, months


def _is_payment_already_processed_best_effort(db: Session, payment_id: str) -> bool:
    candidates = ["ProcessedPayment", "Payment", "PaymentEvent", "MercadoPagoPayment"]
    for name in candidates:
        model_cls = getattr(models, name, None)
        if not model_cls:
            continue

        for field in ["mp_payment_id", "payment_id", "external_id", "provider_payment_id"]:
            if hasattr(model_cls, field):
                try:
                    q = db.query(model_cls).filter(getattr(model_cls, field) == payment_id).first()
                    if q:
                        return True
                except Exception:
                    pass
    return False


def _mark_payment_processed_best_effort(db: Session, payment_id: str) -> None:
    candidates = ["ProcessedPayment", "Payment", "PaymentEvent", "MercadoPagoPayment"]
    for name in candidates:
        model_cls = getattr(models, name, None)
        if not model_cls:
            continue

        for field in ["mp_payment_id", "payment_id", "external_id", "provider_payment_id"]:
            if hasattr(model_cls, field):
                try:
                    obj = model_cls()
                    setattr(obj, field, payment_id)
                    if hasattr(obj, "created_at"):
                        setattr(obj, "created_at", datetime.now(timezone.utc))
                    db.add(obj)
                    return
                except Exception:
                    continue


# ============================================================
# 📩 WEBHOOK MERCADO PAGO
# ============================================================
@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    """
    MODO REAL:
      - extrai payment_id
      - consulta API Mercado Pago (MP_ACCESS_TOKEN)
      - confirma approved
      - lê external_reference (username:plan:months)
      - aplica plano

    MODO TESTE (WEBHOOK_TEST_MODE=True):
      - NÃO chama Mercado Pago
      - usa campos do payload:
          status: "approved"
          external_reference: "username:plan:months"
          payer_email: "email@..."
    """
    _verify_webhook_secret(x_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    # Aceita variações: type/topic
    event_type = payload.get("type") or payload.get("topic") or "payment"

    if event_type not in ("payment", "merchant_order"):
        return {"status": "ignored", "reason": "Evento não suportado"}

    payment_id = _extract_payment_id(payload) or "TEST"
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment_id ausente no webhook")

    # Idempotência best-effort
    if _is_payment_already_processed_best_effort(db, payment_id):
        return {"status": "ignored", "reason": "Pagamento já processado", "payment_id": payment_id}

    # ========================================================
    # ✅ MODO TESTE (sem Mercado Pago)
    # ========================================================
    if getattr(settings, "WEBHOOK_TEST_MODE", False):
        status = (payload.get("status") or "").strip().lower()
        external_reference = (payload.get("external_reference") or "").strip()
        payer_email = (payload.get("payer_email") or "").strip()

        if status != "approved":
            return {"status": "ignored", "reason": "TEST_MODE: Pagamento não aprovado", "payment_id": payment_id}

        username, plan_id, months = _parse_external_reference(external_reference)

        user = db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        apply_paid_plan(user=user, plan_id=plan_id, months=months)

        if payer_email and not user.email:
            user.email = payer_email

        _mark_payment_processed_best_effort(db, payment_id)

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "status": "processed",
            "mode": "test",
            "payment_id": payment_id,
            "username": user.username,
            "plan": user.plan,
            "expires_at": user.plan_expires_at,
        }

    # ========================================================
    # 🔥 MODO REAL (com Mercado Pago)
    # ========================================================
    if not settings.MP_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN ausente no servidor")

    # Import local pra não quebrar import se lib não estiver presente em dev
    try:
        import mercadopago
    except Exception:
        raise HTTPException(status_code=500, detail="Dependência mercadopago não instalada no servidor")

    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    payment = sdk.payment().get(payment_id)
    if payment.get("status") != 200:
        raise HTTPException(status_code=400, detail="Pagamento não encontrado no Mercado Pago")

    payment_data = payment.get("response") or {}

    if (payment_data.get("status") or "").lower() != "approved":
        return {"status": "ignored", "reason": "Pagamento não aprovado", "payment_id": payment_id}

    external_reference = payment_data.get("external_reference") or ""
    username, plan_id, months = _parse_external_reference(external_reference)

    user = db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    apply_paid_plan(user=user, plan_id=plan_id, months=months)

    payer = payment_data.get("payer") or {}
    payer_email = payer.get("email")
    if payer_email and not user.email:
        user.email = payer_email

    _mark_payment_processed_best_effort(db, payment_id)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "processed",
        "mode": "real",
        "payment_id": payment_id,
        "username": user.username,
        "plan": user.plan,
        "expires_at": user.plan_expires_at,
    }
