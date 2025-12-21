from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class BlackLinkUser(Base):
    __tablename__ = "blacklink_users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(150), nullable=True)
    bio = Column(Text, nullable=True)

    # identidade para pagamento / contato (opcional)
    email = Column(String(180), nullable=True, unique=True)

    # aparência / perfil (mantém compatível com templates atuais)
    avatar_url = Column(Text, nullable=True)

    main_cta_url = Column(Text, nullable=True)
    main_cta_label = Column(Text, nullable=True)
    main_cta_subtitle = Column(Text, nullable=True)

    instagram_url = Column(Text, nullable=True)
    tiktok_url = Column(Text, nullable=True)
    youtube_url = Column(Text, nullable=True)
    telegram_url = Column(Text, nullable=True)
    linkedin_url = Column(Text, nullable=True)
    github_url = Column(Text, nullable=True)
    facebook_url = Column(Text, nullable=True)
    kwai_url = Column(Text, nullable=True)
    mercadolivre_url = Column(Text, nullable=True)

    # plano atual (o que governa limites)
    plan = Column(String(20), default="free", nullable=False)

    # ciclo de vida (vendável)
    plan_status = Column(String(20), default="active", nullable=False)  # active | expired | canceled
    plan_started_at = Column(DateTime, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)

    # histórico mínimo do último plano pago
    last_paid_plan = Column(String(20), nullable=True)
    last_paid_expires_at = Column(DateTime, nullable=True)

    # ids do MP/assinatura (se usar)
    mp_customer_id = Column(String(120), nullable=True)
    mp_subscription_id = Column(String(120), nullable=True)

    products = relationship("BlackLinkProduct", back_populates="owner", cascade="all, delete-orphan")


class BlackLinkProduct(Base):
    __tablename__ = "blacklink_products"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("blacklink_users.id"), nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    url = Column(String(600), nullable=True)

    image_url = Column(Text, nullable=True)
    source_image_url = Column(Text, nullable=True)

    price = Column(String(50), nullable=True)

    tag = Column(Text, nullable=True)
    badge = Column(Text, nullable=True)
    cta_label = Column(Text, nullable=True)

    is_active = Column(Integer, default=1)
    is_featured = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("BlackLinkUser", back_populates="products")
