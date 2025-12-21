from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BlackLinkUser
from ..schemas import UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


# ============================================================
# 🔐 AUTH SIMPLES — BASEADO EM USERNAME
# (sem senha / sem JWT — modo DON inicial)
# ============================================================

@router.post("/login", response_model=UserOut)
def login_blacklink(username: str, db: Session = Depends(get_db)):
    """
    Login simples para painel/admin.
    Retorna o usuário se existir.
    """

    user = (
        db.query(BlackLinkUser)
        .filter(BlackLinkUser.username == username.lower().strip())
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Usuário BlackLink não encontrado."
        )

    return user


@router.get("/me/{username}", response_model=UserOut)
def get_me(username: str, db: Session = Depends(get_db)):
    """
    Endpoint utilitário para painel.
    """

    user = (
        db.query(BlackLinkUser)
        .filter(BlackLinkUser.username == username.lower().strip())
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Usuário BlackLink não encontrado."
        )

    return user
