from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any


# ============================================================
# PLANOS OFICIAIS (IDs canônicos)
# ============================================================
PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_DON = "don"

ALL_PLANS = {PLAN_FREE, PLAN_PRO, PLAN_DON}


# ============================================================
# MODELO DO CATÁLOGO
# ============================================================
@dataclass(frozen=True)
class Plan:
    """
    Catálogo único de planos (fonte da verdade).
    - price_brl_cents: preço do plano em centavos (BRL). FREE = 0.
    - duration_days: duração padrão (ex.: 30 dias por "mês").
    - limits: limites técnicos do SaaS.
    - features: lista para UI (checkout/página de preços).
    """
    id: str
    name: str
    price_brl_cents: int
    duration_days: int
    is_sellable: bool
    badge: Optional[str] = None
    highlight: bool = False

    limits: Dict[str, Any] = field(default_factory=dict)
    features: List[str] = field(default_factory=list)


# ============================================================
# CATÁLOGO (AJUSTE AQUI UMA VEZ E O RESTO USA)
# ============================================================
_CATALOG: Dict[str, Plan] = {
    PLAN_FREE: Plan(
        id=PLAN_FREE,
        name="FREE",
        price_brl_cents=0,
        duration_days=0,  # não expira por pagamento (expiração só para planos pagos)
        is_sellable=False,
        badge="Padrão",
        highlight=False,
        limits={
            # LIMITES DO MOTOR SAAS (PASSO 2)
            "max_products": 3,
            "ml_ingest_enabled": False,

            # extras (para evolução)
            "custom_domain": False,
            "themes": 1,
            "support": "community",
        },
        features=[
            "Até 3 produtos na vitrine",
            "Links profissionais (básico)",
            "Sem ingestão automática do Mercado Livre",
            "Suporte comunitário",
        ],
    ),
    PLAN_PRO: Plan(
        id=PLAN_PRO,
        name="PRO",
        price_brl_cents=1990,  # R$ 19,90 / mês (ajuste depois)
        duration_days=30,
        is_sellable=True,
        badge="Mais vendido",
        highlight=True,
        limits={
            "max_products": 30,
            "ml_ingest_enabled": True,

            "custom_domain": False,
            "themes": 3,
            "support": "priority",
        },
        features=[
            "Até 30 produtos na vitrine",
            "Ingestão automática do Mercado Livre (permitida)",
            "Destaque em vitrine (prioridade)",
            "3 temas/skins",
            "Suporte prioritário",
        ],
    ),
    PLAN_DON: Plan(
        id=PLAN_DON,
        name="DON",
        price_brl_cents=4990,  # R$ 49,90 / mês (ajuste depois)
        duration_days=30,
        is_sellable=True,
        badge="Ultra Premium",
        highlight=False,
        limits={
            "max_products": 200,
            "ml_ingest_enabled": True,

            "custom_domain": True,
            "themes": 10,
            "support": "vip",
        },
        features=[
            "Até 200 produtos na vitrine",
            "Ingestão automática do Mercado Livre (permitida)",
            "Destaque máximo (homepage / vitrine premium)",
            "Domínio próprio (quando ativarmos)",
            "10 temas/skins",
            "Suporte VIP",
        ],
    ),
}


# ============================================================
# HELPERS (API interna do catálogo)
# ============================================================
def normalize_plan(plan: Optional[str]) -> str:
    if not plan:
        return PLAN_FREE
    p = str(plan).strip().lower()
    return p if p in ALL_PLANS else PLAN_FREE


def get_plan(plan: Optional[str]) -> Plan:
    p = normalize_plan(plan)
    return _CATALOG[p]


def list_plans(include_free: bool = True, sellable_only: bool = False) -> List[Plan]:
    plans = list(_CATALOG.values())
    if not include_free:
        plans = [p for p in plans if p.id != PLAN_FREE]
    if sellable_only:
        plans = [p for p in plans if p.is_sellable]
    # ordem fixa para UI
    order = {PLAN_FREE: 0, PLAN_PRO: 1, PLAN_DON: 2}
    plans.sort(key=lambda x: order.get(x.id, 99))
    return plans


def price_brl(plan: Plan) -> float:
    # exibição simples (UI)
    return plan.price_brl_cents / 100.0


def calc_plan_expiry(start_at: datetime, months: int, plan_id: str) -> Optional[datetime]:
    """
    Regras:
    - FREE não tem expiração por pagamento → None
    - PRO/DON: expira start + (duration_days * months)
    """
    plan = get_plan(plan_id)

    if plan.id == PLAN_FREE:
        return None

    m = int(months) if months is not None else 1
    if m < 1:
        m = 1

    # normaliza timezone
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)

    total_days = plan.duration_days * m
    return start_at + timedelta(days=total_days)


def limits_for(plan_id: Optional[str]) -> Dict[str, Any]:
    return dict(get_plan(plan_id).limits)


def is_ml_ingest_enabled(plan_id: Optional[str]) -> bool:
    return bool(get_plan(plan_id).limits.get("ml_ingest_enabled", False))


def max_products(plan_id: Optional[str]) -> int:
    return int(get_plan(plan_id).limits.get("max_products", 0))


def as_public_dict(plan: Plan) -> Dict[str, Any]:
    """
    Para UI/checkout: sem expor coisas internas desnecessárias.
    """
    return {
        "id": plan.id,
        "name": plan.name,
        "badge": plan.badge,
        "highlight": plan.highlight,
        "price_brl_cents": plan.price_brl_cents,
        "price_brl": price_brl(plan),
        "duration_days": plan.duration_days,
        "is_sellable": plan.is_sellable,
        "limits": dict(plan.limits),
        "features": list(plan.features),
    }
