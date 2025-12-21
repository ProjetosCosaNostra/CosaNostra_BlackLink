from __future__ import annotations

import os
from typing import Dict, Any

import mercadopago

from app.services.plan_catalog import get_plan, price_brl


# ============================================================
# CLIENTE MERCADO PAGO
# ============================================================
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

if not MP_ACCESS_TOKEN:
    raise RuntimeError("MP_ACCESS_TOKEN não configurado no .env")

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)


# ============================================================
# CRIAR PREFERENCE
# ============================================================
def create_payment_preference(
    *,
    username: str,
    plan_id: str,
    months: int,
    email: str | None = None,
    success_url: str,
    failure_url: str,
    pending_url: str,
) -> Dict[str, Any]:
    plan = get_plan(plan_id)

    if not plan.is_sellable:
        raise ValueError("Plano não vendável")

    months = max(1, int(months))
    unit_price = price_brl(plan) * months

    preference_data = {
        "items": [
            {
                "id": f"{plan.id}_{months}",
                "title": f"Plano {plan.name} — {months} mês(es)",
                "description": f"CosaNostra BlackLink — Plano {plan.name}",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(unit_price),
            }
        ],
        "payer": {
            "email": email or "comprador@blacklink.local",
        },
        "metadata": {
            "username": username,
            "plan": plan.id,
            "months": months,
            "email": email,
        },
        "back_urls": {
            "success": success_url,
            "failure": failure_url,
            "pending": pending_url,
        },
        "auto_return": "approved",
        "notification_url": success_url.replace("/success", "/webhook/mercadopago"),
        "statement_descriptor": "BLACKLINK",
        "binary_mode": True,
    }

    preference_response = sdk.preference().create(preference_data)

    if preference_response.get("status") != 201:
        raise RuntimeError("Erro ao criar preference Mercado Pago")

    return preference_response["response"]
