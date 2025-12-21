from __future__ import annotations

from typing import List, Optional
from pathlib import Path
from datetime import datetime
from dateutil.parser import isoparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.plan_manager import sync_user_plan

router = APIRouter(tags=["BlackLink"])

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --------------------------------------------------
# UTILS
# --------------------------------------------------
def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return isoparse(value)


def _get_user_by_username(db: Session, username: str) -> models.BlackLinkUser:
    username = username.lower().strip()
    user = db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário BlackLink não encontrado.")
    return sync_user_plan(db, user)


# --------------------------------------------------
# CRUD
# --------------------------------------------------
@router.post("/blacklink/", response_model=schemas.UserOut)
def create_blacklink_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    username = user_in.username.lower().strip()
    if db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first():
        raise HTTPException(status_code=400, detail="Username já está em uso.")

    data = user_in.model_dump()
    data["username"] = username

    # 🔥 FIX PASSO 3 — converter strings ISO → datetime
    data["plan_started_at"] = _parse_dt(data.get("plan_started_at"))
    data["plan_expires_at"] = _parse_dt(data.get("plan_expires_at"))
    data["last_paid_expires_at"] = _parse_dt(data.get("last_paid_expires_at"))

    user = models.BlackLinkUser(**data)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/blacklink/{username}", response_model=schemas.UserOut)
def get_blacklink_user(username: str, db: Session = Depends(get_db)):
    return _get_user_by_username(db, username)


@router.patch("/blacklink/{username}", response_model=schemas.UserOut)
def update_blacklink_user(username: str, user_update: schemas.UserUpdate, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    data = user_update.model_dump(exclude_unset=True)

    # 🔥 FIX PASSO 3 — converter datas
    if "plan_started_at" in data:
        data["plan_started_at"] = _parse_dt(data["plan_started_at"])
    if "plan_expires_at" in data:
        data["plan_expires_at"] = _parse_dt(data["plan_expires_at"])
    if "last_paid_expires_at" in data:
        data["last_paid_expires_at"] = _parse_dt(data["last_paid_expires_at"])

    for field, value in data.items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/blacklink/", response_model=List[schemas.UserOut])
def list_blacklink_users(plan: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.BlackLinkUser)
    if plan:
        q = q.filter(models.BlackLinkUser.plan == plan)
    return q.all()


@router.delete("/blacklink/{username}", status_code=204)
def delete_blacklink_user(username: str, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    db.delete(user)
    db.commit()
    return None


# --------------------------------------------------
# PÁGINA PÚBLICA
# --------------------------------------------------
@router.get("/u/{username}", response_class=HTMLResponse)
def public_blacklink_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    products = (
        db.query(models.BlackLinkProduct)
        .filter(models.BlackLinkProduct.owner_id == user.id)
        .all()
    )

    return templates.TemplateResponse(
        "blacklink_don.html",
        {
            "request": request,
            "username": user.username,
            "display_name": user.display_name,
            "bio": user.bio,
            "avatar_url": user.avatar_url,
            "main_cta_url": user.main_cta_url,
            "main_cta_label": user.main_cta_label,
            "main_cta_subtitle": user.main_cta_subtitle,
            "instagram_url": user.instagram_url,
            "tiktok_url": user.tiktok_url,
            "youtube_url": user.youtube_url,
            "telegram_url": user.telegram_url,
            "linkedin_url": user.linkedin_url,
            "github_url": user.github_url,
            "facebook_url": user.facebook_url,
            "kwai_url": user.kwai_url,
            "mercadolivre_url": user.mercadolivre_url,
            "products": products,
            "plan": user.plan,
            "plan_status": user.plan_status,
        },
    )
