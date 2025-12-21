from __future__ import annotations

from typing import Dict, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema(db_engine) -> None:
    """
    SQLite: adiciona colunas faltantes sem Alembic (ALTER TABLE ... ADD COLUMN ...).
    PASSO 3: garante colunas de ciclo de vida do plano.
    """
    if not str(db_engine.url).startswith("sqlite"):
        return

    user_cols: Dict[str, str] = {
        "display_name": "VARCHAR(150)",
        "bio": "TEXT",

        "email": "VARCHAR(180)",
        "avatar_url": "TEXT",

        "main_cta_url": "TEXT",
        "main_cta_label": "TEXT",
        "main_cta_subtitle": "TEXT",

        "instagram_url": "TEXT",
        "tiktok_url": "TEXT",
        "youtube_url": "TEXT",
        "telegram_url": "TEXT",
        "linkedin_url": "TEXT",
        "github_url": "TEXT",
        "facebook_url": "TEXT",
        "kwai_url": "TEXT",
        "mercadolivre_url": "TEXT",

        "plan": "VARCHAR(20)",

        # PASSO 3
        "plan_status": "VARCHAR(20)",
        "plan_started_at": "DATETIME",
        "plan_expires_at": "DATETIME",
        "last_paid_plan": "VARCHAR(20)",
        "last_paid_expires_at": "DATETIME",

        "mp_customer_id": "VARCHAR(120)",
        "mp_subscription_id": "VARCHAR(120)",
    }

    product_cols: Dict[str, str] = {
        "description": "TEXT",
        "url": "VARCHAR(600)",
        "image_url": "TEXT",
        "source_image_url": "TEXT",
        "price": "VARCHAR(50)",
        "tag": "TEXT",
        "badge": "TEXT",
        "cta_label": "TEXT",
        "created_at": "DATETIME",
    }

    def table_exists(conn, table: str) -> bool:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchone()
        return row is not None

    def existing_cols(conn, table: str):
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}

    with db_engine.connect() as conn:
        if table_exists(conn, "blacklink_users"):
            existing = existing_cols(conn, "blacklink_users")
            for col, coltype in user_cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE blacklink_users ADD COLUMN {col} {coltype}"))

        if table_exists(conn, "blacklink_products"):
            existing = existing_cols(conn, "blacklink_products")
            for col, coltype in product_cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE blacklink_products ADD COLUMN {col} {coltype}"))

        conn.commit()
