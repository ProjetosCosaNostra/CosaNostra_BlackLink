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
    Se settings.MP_WEBHOOK_SECRET estiver definido, exige:
    X-Webhook-Secret: <segredo>
    """
    secret = getattr(settings, "MP_WEBHOOK_SECRET", None)
    if secret:
        if not x_webhook_secret or x_webhook_secret != secret:
            raise HTTPException(status_code=403, detail="Webhook não autorizado")


# ============================================================
# 🧪 TEST MODE
# ============================================================
def _is_test_mode() -> bool:
    """
    Liga modo teste via env var:
    WEBHOOK_TEST_MODE=1 (Railway Variables)
    """
    v = getattr(settings, "WEBHOOK_TEST_MODE", None)
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


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
    """
    MercadoPago envia variações. Tentamos cobrir todas:
    - payload.data.id
    - payload.id
    - payload.data_id
    - payload.resource (url) -> último segmento
    """
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
    Esperado (compatível com /payment/checkout):
      username:plan:months
    """
    if not external_reference or ":" not in external_reference:
        raise HTTPException(status_code=400, detail="external_reference inválido")

    parts = external_reference.split(":")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="external_reference inválido")

    username = parts[0].strip().lower()
    plan_id = normalize_plan(parts[1].strip())
    try:
        months = int(parts[2])
    except Exception:
        raise HTTPException(status_code=400, detail="months inválido no external_reference")

    if not username:
        raise HTTPException(status_code=400, detail="username inválido no external_reference")
    if plan_id == PLAN_FREE:
        raise HTTPException(status_code=400, detail="Plano FREE não é vendável")
    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="months inválido (1..24)")

    return username, plan_id, months


def _is_payment_already_processed_best_effort(db: Session, payment_id: str) -> bool:
    """
    Idempotência best-effort:
    - se existir algum model/tabela que guarde payment_id, usa.
    - se não existir, retorna False e segue o fluxo (não quebra).
    """
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
    """
    Tenta registrar payment_id em algum model existente.
    Se não existir, ignora silenciosamente.
    """
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
# 📩 WEBHOOK MERCADO PAGO (PRODUÇÃO + TEST MODE)
# ============================================================
@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    """
    Produção:
      - extrai payment_id
      - consulta MercadoPago API (sdk) e valida "approved"
      - usa external_reference real do pagamento

    Test mode (WEBHOOK_TEST_MODE=1):
      - NÃO chama sdk
      - usa o payload (status/external_reference/payer_email)
      - permite testar sem gastar 1 real
    """
    _verify_webhook_secret(x_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    # MercadoPago pode mandar 'type' (payment) ou 'topic' (payment/merchant_order)
    event_type = (payload.get("type") or payload.get("topic") or "payment").strip()

    # aceitamos payment e merchant_order (merchant_order às vezes aponta para pagamento)
    if event_type not in ("payment", "merchant_order"):
        return {"status": "ignored", "reason": "Evento não suportado", "event_type": event_type}

    payment_id = _extract_payment_id(payload) or "NO-ID"

    # Idempotência best-effort (se existir tabela)
    if payment_id != "NO-ID" and _is_payment_already_processed_best_effort(db, payment_id):
        return {"status": "ignored", "reason": "Pagamento já processado", "payment_id": payment_id}

    # ========================================================
    # 🧪 TEST MODE: usa o payload direto
    # ========================================================
    if _is_test_mode():
        status = (payload.get("status") or "").strip().lower()
        external_reference = (payload.get("external_reference") or "").strip()

        if status != "approved":
            return {
                "status": "ignored",
                "mode": "test",
                "reason": "status não aprovado",
                "payment_id": payment_id,
                "received_status": status,
            }

        username, plan_id, months = _parse_external_reference(external_reference)

        user = (
            db.query(models.BlackLinkUser)
            .filter(models.BlackLinkUser.username == username)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        apply_paid_plan(user=user, plan_id=plan_id, months=months)

        payer_email = payload.get("payer_email")
        if payer_email and not getattr(user, "email", None):
            user.email = payer_email

        if payment_id != "NO-ID":
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
    # PRODUÇÃO: consulta Mercado Pago — fonte de verdade
    # ========================================================
    if not getattr(settings, "MP_ACCESS_TOKEN", None):
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN ausente no servidor")

    if payment_id == "NO-ID":
        raise HTTPException(status_code=400, detail="payment_id ausente no webhook")

    import mercadopago

    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
    payment = sdk.payment().get(payment_id)

    if payment.get("status") != 200:
        raise HTTPException(status_code=400, detail="Pagamento não encontrado no Mercado Pago")

    payment_data = payment.get("response") or {}

    if (payment_data.get("status") or "").lower() != "approved":
        return {"status": "ignored", "reason": "Pagamento não aprovado", "payment_id": payment_id}

    external_reference = (payment_data.get("external_reference") or "").strip()
    username, plan_id, months = _parse_external_reference(external_reference)

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    apply_paid_plan(user=user, plan_id=plan_id, months=months)

    payer = payment_data.get("payer") or {}
    payer_email = payer.get("email")
    if payer_email and not getattr(user, "email", None):
        user.email = payer_email

    _mark_payment_processed_best_effort(db, payment_id)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "processed",
        "mode": "production",
        "payment_id": payment_id,
        "username": user.username,
        "plan": user.plan,
        "expires_at": user.plan_expires_at,
    }
