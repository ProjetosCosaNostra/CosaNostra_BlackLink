from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BlackLinkUser
from app.schemas import AdminCreateUser  # ✅ novo schema (JSON body)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# ============================================================
# POST /admin/create-user
# Criação profissional via JSON (SaaS padrão)
# ============================================================
@router.post("/create-user", status_code=201)
def create_user_admin(
    payload: AdminCreateUser,
    db: Session = Depends(get_db),
):
    # normalização
    username = (payload.username or "").strip().lower()
    email = (payload.email or "").strip().lower()
    plan = (payload.plan or "free").lower().strip()

    # validações básicas
    if not username:
        raise HTTPException(status_code=400, detail="username é obrigatório")

    if not email:
        raise HTTPException(status_code=400, detail="email é obrigatório")

    if plan not in {"free", "pro", "don"}:
        raise HTTPException(
            status_code=400,
            detail="Plano inválido. Use: free, pro ou don"
        )

    # usuário já existe?
    existing = db.query(BlackLinkUser).filter(
        BlackLinkUser.username == username
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Usuário '{username}' já existe"
        )

    # cria usuário
    user = BlackLinkUser(
        username=username,
        email=email,
        plan=plan,
        plan_status="active",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "plan": user.plan,
        "status": "created"
    }
