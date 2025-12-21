from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class PlanPolicy:
    product_limit: Optional[int]  # None = ilimitado
    can_ingest: bool
    default_days: int


PLAN_POLICIES = {
    "free": PlanPolicy(product_limit=3, can_ingest=False, default_days=0),
    "pro":  PlanPolicy(product_limit=20, can_ingest=True, default_days=30),
    "don":  PlanPolicy(product_limit=None, can_ingest=True, default_days=30),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_plan(plan: Optional[str]) -> str:
    p = (plan or "free").strip().lower()
    return p if p in PLAN_POLICIES else "free"


def get_policy(plan: Optional[str]) -> PlanPolicy:
    return PLAN_POLICIES[normalize_plan(plan)]


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_expired(plan_expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if not plan_expires_at:
        return False
    now = now or utcnow()
    return _as_utc(plan_expires_at) < _as_utc(now)


def sync_user_plan(db: Session, user: models.BlackLinkUser, now: Optional[datetime] = None) -> models.BlackLinkUser:
    """
    PASSO 3:
    - Se pro/don expirou: downgrade para FREE automaticamente
    - plan_status vira "expired"
    """
    now = now or utcnow()
    current_plan = normalize_plan(user.plan)

    if is_expired(user.plan_expires_at, now=now):
        # guarda histórico
        user.last_paid_plan = user.last_paid_plan or current_plan
        user.last_paid_expires_at = user.last_paid_expires_at or user.plan_expires_at

        user.plan = "free"
        user.plan_status = "expired"
        user.plan_started_at = None
        user.plan_expires_at = None

        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # se não expirou, normaliza status
    if current_plan in ("pro", "don"):
        user.plan_status = "active"
    else:
        user.plan = "free"
        user.plan_status = user.plan_status or "active"

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def apply_paid_plan(db: Session, user: models.BlackLinkUser, plan: str, months: int = 1, now: Optional[datetime] = None) -> models.BlackLinkUser:
    """
    Base vendável: aplica pro/don com expiração.
    """
    now = now or utcnow()
    plan = normalize_plan(plan)
    if plan == "free":
        plan = "pro"

    months = max(int(months or 1), 1)
    policy = get_policy(plan)
    expires = now + timedelta(days=policy.default_days * months)

    user.plan = plan
    user.plan_status = "active"
    user.plan_started_at = now
    user.plan_expires_at = expires
    user.last_paid_plan = plan
    user.last_paid_expires_at = expires

    db.add(user)
    db.commit()
    db.refresh(user)
    return user
