from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..config import TEMPLATES_DIR

router = APIRouter(tags=["Painel DON"])

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_user_by_username(db: Session, username: str) -> models.BlackLinkUser:
    username = username.lower().strip()
    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuário BlackLink não encontrado.")
    return user


@router.get("/{username}", response_class=HTMLResponse)
def painel_usuario(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Painel DON Ultra Premium para o dono do BlackLink.

    URL final (local):
      http://localhost:8000/painel/{username}

    Template:
      templates/user_panel.html
    """
    user = _get_user_by_username(db, username)

    return templates.TemplateResponse(
        "user_panel.html",
        {
            "request": request,
            "username": user.username,
        },
    )
