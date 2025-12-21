from __future__ import annotations

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ============================================================
# PRODUCTS
# ============================================================
class ProductBase(BaseModel):
    title: str
    description: Optional[str] = None
    url: Optional[str] = None

    image_url: Optional[str] = None
    source_image_url: Optional[str] = None

    price: Optional[str] = None
    tag: Optional[str] = None
    badge: Optional[str] = None
    cta_label: Optional[str] = "Ver oferta"

    is_featured: Optional[int] = 0
    is_active: Optional[int] = 1


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    source_image_url: Optional[str] = None
    price: Optional[str] = None
    tag: Optional[str] = None
    badge: Optional[str] = None
    cta_label: Optional[str] = None
    is_featured: Optional[int] = None
    is_active: Optional[int] = None


class ProductOut(ProductBase):
    id: int
    owner_id: int
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# USERS
# ============================================================
class UserBase(BaseModel):
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[str] = None

    avatar_url: Optional[str] = None

    main_cta_url: Optional[str] = None
    main_cta_label: Optional[str] = None
    main_cta_subtitle: Optional[str] = None

    instagram_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    youtube_url: Optional[str] = None
    telegram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    facebook_url: Optional[str] = None
    kwai_url: Optional[str] = None
    mercadolivre_url: Optional[str] = None

    plan: Optional[str] = "free"

    # STATUS DE PLANO — sempre datetime real (ORM-safe)
    plan_status: Optional[str] = "active"
    plan_started_at: Optional[datetime] = None
    plan_expires_at: Optional[datetime] = None
    last_paid_plan: Optional[str] = None
    last_paid_expires_at: Optional[datetime] = None


class UserCreate(UserBase):
    """
    Entrada pode mandar datetime em ISO.
    Pydantic converte automaticamente.
    """
    pass


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None

    main_cta_url: Optional[str] = None
    main_cta_label: Optional[str] = None
    main_cta_subtitle: Optional[str] = None

    instagram_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    youtube_url: Optional[str] = None
    telegram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    facebook_url: Optional[str] = None
    kwai_url: Optional[str] = None
    mercadolivre_url: Optional[str] = None

    plan: Optional[str] = None
    plan_status: Optional[str] = None
    plan_started_at: Optional[datetime] = None
    plan_expires_at: Optional[datetime] = None
    last_paid_plan: Optional[str] = None
    last_paid_expires_at: Optional[datetime] = None


class UserOut(UserBase):
    id: int
    products: List[ProductOut] = []
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# ADMIN / INGEST
# ============================================================
class AdminIngestRequest(BaseModel):
    username: str
    ml_url: str
    featured: int = 1


# ============================================================
# PAYMENTS (PRODUÇÃO-SAFE)
# ============================================================
class PaymentProcessRequest(BaseModel):
    """
    - Em SANDBOX: payment_id pode ser omitido
    - Em PRODUÇÃO: payment_id é OBRIGATÓRIO
    """
    username: str
    plan: str  # pro | don
    months: int = 1
    email: Optional[str] = None

    # CRÍTICO PARA PRODUÇÃO
    payment_id: Optional[str] = None


class PaymentProcessResponse(BaseModel):
    status: str
    message: str
    username: str
    plan: str
    plan_status: str
    plan_expires_at: Optional[datetime] = None
