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

import logging

logger = logging.getLogger("blacklink")

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# ============================================================
# 🔐 Segurança opcional (recomendado)
# ============================================================
def _verify_webhook_secret(x_webhook_secret: Optional[str]) -> None:
    """
    Proteção simples (opcional) para evitar chamadas diretas ao webhook.
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
        and getattr(user, "plan_status", None) == "active"
        and getattr(user, "plan_expires_at", None)
        and user.plan_expires_at > now
    ):
        start_at = user.plan_expires_at
    else:
        start_at = now

    expires_at = calc_plan_expiry(start_at, months, plan.id)

    # Histórico
    if user.plan in ("pro", "don"):
        if hasattr(user, "last_paid_plan"):
            user.last_paid_plan = user.plan
        if hasattr(user, "last_paid_expires_at"):
            user.last_paid_expires_at = getattr(user, "plan_expires_at", None)

    user.plan = plan.id
    if hasattr(user, "plan_status"):
        user.plan_status = "active"
    if hasattr(user, "plan_started_at"):
        user.plan_started_at = start_at
    if hasattr(user, "plan_expires_at"):
        user.plan_expires_at = expires_at


# ============================================================
# 🧩 Helpers
# ============================================================
def _extract_payment_id(payload: Dict[str, Any]) -> Optional[str]:
    """
    Mercado Pago pode mandar variações.
    Preferimos:
    - payload["data"]["id"]
    - payload["id"]
    - payload["data_id"] (raros)
    - payload["resource"] (URL com id no final)
    """
    data = payload.get("data") or {}
    pid = data.get("id") or payload.get("id") or payload.get("data_id")
    if pid:
        return str(pid)

    resource = payload.get("resource")
    if isinstance(resource, str) and resource.strip():
        # Ex: https://api.mercadopago.com/v1/payments/123456
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
    """
    Idempotência BEST-EFFORT:
    - Se houver algum model/tabela de pagamentos no seu projeto, tenta consultar.
    - Se não existir, não quebra o webhook (retorna False).
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
    Se existir algum model/tabela compatível, tenta salvar.
    Se não existir, não faz nada.
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


def _bool_env(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _test_mode_enabled() -> bool:
    # Aceita tanto o campo do settings quanto env var direta (pra não te travar)
    if getattr(settings, "WEBHOOK_TEST_MODE", None) is True:
        return True
    return _bool_env(getattr(settings, "WEBHOOK_TEST_MODE", None))


# ============================================================
# 🌐 Consulta Mercado Pago COM TIMEOUT (evita 502 no Railway)
# ============================================================
def _fetch_mp_payment(payment_id: str) -> Dict[str, Any]:
    """
    Busca pagamento no Mercado Pago via HTTP direto, com timeout curto
    pra não travar o serviço no Railway.
    """
    if not settings.MP_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="MP_ACCESS_TOKEN ausente no servidor")

    import httpx

    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
    except Exception as e:
        logger.exception("Falha ao consultar Mercado Pago (timeout/rede).")
        raise HTTPException(status_code=502, detail="Falha ao consultar Mercado Pago") from e

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Pagamento não encontrado no Mercado Pago")

    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Resposta inválida do Mercado Pago")


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
    Webhook Mercado Pago.

    ✅ Produção:
    1) Recebe evento
    2) Extrai payment_id
    3) Consulta MP (timeout curto)
    4) Confirma status approved
    5) Lê external_reference (username:plan:months)
    6) Aplica plano (idempotente best-effort)

    ✅ Test mode (sem dinheiro / sem pagamento real):
    - Habilite WEBHOOK_TEST_MODE=1 no Railway
    - Envie payload com:
        {
          "type":"payment",
          "data":{"id":"TEST-123"},
          "external_reference":"felipe:pro:1",
          "status":"approved",
          "payer_email":"felipe@exemplo.com"
        }
    - Nesse modo NÃO chama Mercado Pago.
    """

    _verify_webhook_secret(x_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    event_type = payload.get("type") or payload.get("topic")

    # Só processa pagamentos
    if event_type not in ("payment", "merchant_order"):
        return {"status": "ignored", "reason": "Evento não suportado"}

    payment_id = _extract_payment_id(payload)
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment_id ausente no webhook")

    # Idempotência best-effort
    if _is_payment_already_processed_best_effort(db, payment_id):
        return {"status": "ignored", "reason": "Pagamento já processado", "payment_id": payment_id}

    # ========================================================
    # ✅ TEST MODE (não consulta MP)
    # ========================================================
    test_mode = _bool_env(str(getattr(settings, "WEBHOOK_TEST_MODE", ""))) or _bool_env(str(payload.get("test_mode")))
    if test_mode:
        # status e reference vêm do próprio payload
        status = (payload.get("status") or "approved").lower()
        if status != "approved":
            return {"status": "ignored", "reason": "Pagamento de teste não aprovado", "payment_id": payment_id}

        external_reference = payload.get("external_reference") or ""
        if not external_reference:
            raise HTTPException(status_code=400, detail="external_reference ausente no TEST MODE")

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
        if payer_email and hasattr(user, "email") and not user.email:
            user.email = payer_email

        _mark_payment_processed_best_effort(db, payment_id)

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "status": "processed_test",
            "payment_id": payment_id,
            "username": user.username,
            "plan": user.plan,
            "expires_at": getattr(user, "plan_expires_at", None),
        }

    # ========================================================
    # ✅ PRODUÇÃO (consulta MP com timeout)
    # ========================================================
    mp_payment = _fetch_mp_payment(payment_id)

    if (mp_payment.get("status") or "").lower() != "approved":
        return {"status": "ignored", "reason": "Pagamento não aprovado", "payment_id": payment_id}

    external_reference = mp_payment.get("external_reference") or ""
    username, plan_id, months = _parse_external_reference(external_reference)

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    apply_paid_plan(user=user, plan_id=plan_id, months=months)

    payer = mp_payment.get("payer") or {}
    payer_email = payer.get("email")
    if payer_email and hasattr(user, "email") and not user.email:
        user.email = payer_email

    _mark_payment_processed_best_effort(db, payment_id)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "processed",
        "payment_id": payment_id,
        "username": user.username,
        "plan": user.plan,
        "expires_at": getattr(user, "plan_expires_at", None),
    }
