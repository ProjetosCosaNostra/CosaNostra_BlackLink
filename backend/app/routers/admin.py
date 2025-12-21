from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import BlackLinkUser

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# ============================================================
# POST /admin/create-user
# Criação manual de usuário (BOOTSTRAP / MVP)
# ============================================================
@router.post("/create-user", status_code=201)
def create_user_admin(
    username: str,
    email: str,
    plan: Optional[str] = "free",
    db: Session = Depends(get_db),
):
    # normalização
    username = username.strip().lower()
    plan = (plan or "free").lower()

    # validações básicas
    if not username:
        raise HTTPException(status_code=400, detail="username é obrigatório")

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
