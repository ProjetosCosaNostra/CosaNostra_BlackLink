from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import models, schemas
from ..database import get_db
from ..config import USERS_DIR, TEMPLATES_DIR

router = APIRouter(
    prefix="/api/blacklinks",
    tags=["blacklinks"]
)

# Ambiente Jinja2 para renderizar user_page.html
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"])
)


@router.post("/", response_model=schemas.BlackLinkOut)
def create_blacklink(payload: schemas.BlackLinkCreate, db: Session = Depends(get_db)):
    username = payload.username.lower().strip()

    if not username.isalnum():
        raise HTTPException(
            status_code=400,
            detail="O nome de usuário deve conter apenas letras e números."
        )

    # Já existe?
    existing = db.query(models.BlackLink).filter_by(username=username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nome de usuário já existe.")

    # Carrega template
    try:
        template = env.get_template("user_page.html")
    except Exception:
        raise HTTPException(status_code=500, detail="Template user_page.html não encontrado.")

    # Renderiza HTML com dados básicos
    html_content = template.render(
        username=username,
        theme=payload.theme
    )

    # /users/<username>/index.html
    user_dir: Path = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)

    index_file = user_dir / "index.html"
    index_file.write_text(html_content, encoding="utf-8")

    # Grava no banco
    bl = models.BlackLink(username=username, theme=payload.theme)
    db.add(bl)
    db.commit()
    db.refresh(bl)

    url_path = f"/users/{username}/"

    return schemas.BlackLinkOut(
        username=bl.username,
        theme=bl.theme,
        url_path=url_path
    )
