from __future__ import annotations

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

import mercadopago

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
# 🔐 Segurança opcional (Header Secret)
# ============================================================
def _verify_webhook_secret(x_webhook_secret: Optional[str]) -> None:
    secret = getattr(settings, "MP_WEBHOOK_SECRET", None)
    if secret:
        if not x_webhook_secret or x_webhook_secret != secret:
            raise HTTPException(status_code=403, detail="Webhook não autorizado")


# ============================================================
# 🧪 TEST MODE
# ============================================================
def _is_test_mode() -> bool:
    v = getattr(settings, "WEBHOOK_TEST_MODE", None)
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ============================================================
# 🔧 Aplicar plano pago
# ============================================================
def apply_paid_plan(*, user: models.BlackLinkUser, plan_id: str, months: int) -> None:
    plan = get_plan(plan_id)
    if not plan.is_sellable:
        raise HTTPException(status_code=400, detail="Plano não vendável")

    now = datetime.now(timezone.utc)

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
        return resource.rstrip("/").split("/")[-1]

    return None


def _parse_external_reference(external_reference: str) -> Tuple[str, str, int]:
    if not external_reference or ":" not in external_reference:
        raise HTTPException(status_code=400, detail="external_reference inválido")

    username, plan_raw, months_raw = external_reference.split(":", 2)
    plan_id = normalize_plan(plan_raw)

    try:
        months = int(months_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="months inválido")

    if not username:
        raise HTTPException(status_code=400, detail="username inválido")
    if plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Plano FREE não é vendável")
    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="months inválido (1..24)")

    return username.lower(), plan_id, months


# ============================================================
# 🧠 Idempotência (best-effort)
# ============================================================
def _already_processed(db: Session, payment_id: str) -> bool:
    for model_name in ("ProcessedPayment", "Payment", "PaymentEvent", "MercadoPagoPayment"):
        model_cls = getattr(models, model_name, None)
        if not model_cls:
            continue
        for field in ("mp_payment_id", "payment_id", "external_id"):
            if hasattr(model_cls, field):
                if db.query(model_cls).filter(getattr(model_cls, field) == payment_id).first():
                    return True
    return False


def _mark_processed(db: Session, payment_id: str) -> None:
    for model_name in ("ProcessedPayment", "Payment", "PaymentEvent", "MercadoPagoPayment"):
        model_cls = getattr(models, model_name, None)
        if not model_cls:
            continue
        for field in ("mp_payment_id", "payment_id", "external_id"):
            if hasattr(model_cls, field):
                obj = model_cls()
                setattr(obj, field, payment_id)
                if hasattr(obj, "created_at"):
                    obj.created_at = datetime.now(timezone.utc)
                db.add(obj)
                return


# ============================================================
# 📩 WEBHOOK MERCADO PAGO (FINAL / CORRIGIDO)
# ============================================================
@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    _verify_webhook_secret(x_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    # ========================================================
    # 🧪 TEST MODE — NÃO EXIGE payment_id
    # ========================================================
    if _is_test_mode():
        status = (payload.get("status") or "").lower()
        if status != "approved":
            return {"status": "ignored", "mode": "test"}

        external_reference = payload.get("external_reference", "")
        username, plan_id, months = _parse_external_reference(external_reference)

        user = db.query(models.BlackLinkUser).filter_by(username=username).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        apply_paid_plan(user=user, plan_id=plan_id, months=months)
        db.commit()

        return {
            "status": "processed",
            "mode": "test",
            "username": user.username,
            "plan": user.plan,
        }

    # ========================================================
    # 🚀 PRODUÇÃO — payment_id OBRIGATÓRIO
    # ========================================================
    payment_id = _extract_payment_id(payload)
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment_id ausente")

    if _already_processed(db, payment_id):
        return {"status": "ignored", "reason": "Pagamento já processado"}

    token = (settings.MP_ACCESS_TOKEN or "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN ausente")

    sdk = mercadopago.SDK(token)
    mp_payment = sdk.payment().get(payment_id)

    if mp_payment.get("status") != 200:
        raise HTTPException(status_code=400, detail="Pagamento não encontrado no MP")

    data = mp_payment["response"]
    if data.get("status") != "approved":
        return {"status": "ignored", "reason": "Pagamento não aprovado"}

    username, plan_id, months = _parse_external_reference(
        data.get("external_reference", "")
    )

    user = db.query(models.BlackLinkUser).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    apply_paid_plan(user=user, plan_id=plan_id, months=months)

    payer_email = (data.get("payer") or {}).get("email")
    if payer_email and not user.email:
        user.email = payer_email

    _mark_processed(db, payment_id)
    db.commit()

    return {
        "status": "processed",
        "mode": "production",
        "username": user.username,
        "plan": user.plan,
        "expires_at": user.plan_expires_at,
    }
