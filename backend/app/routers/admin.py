from __future__ import annotations

import httpx
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.schemas import AdminIngestRequest
from app.services.plan_manager import get_policy, normalize_plan, sync_user_plan

router = APIRouter(prefix="/admin", tags=["Admin Auto"])


def _get_user(db: Session, username: str) -> models.BlackLinkUser:
    username = username.lower().strip()
    user = db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return sync_user_plan(db, user)


def _enforce_product_limit(db: Session, user: models.BlackLinkUser) -> None:
    plan = normalize_plan(user.plan)
    policy = get_policy(plan)
    limit = policy.product_limit
    if limit is None:
        return
    count = db.query(models.BlackLinkProduct).filter(models.BlackLinkProduct.owner_id == user.id).count()
    if count >= limit:
        raise HTTPException(status_code=403, detail=f"Limite de produtos do plano {plan.upper()} atingido ({limit}).")


@router.post("/ingest")
def ingest_product_auto(payload: AdminIngestRequest, db: Session = Depends(get_db)):
    user = _get_user(db, payload.username)

    plan = normalize_plan(user.plan)
    policy = get_policy(plan)

    if not policy.can_ingest:
        raise HTTPException(status_code=403, detail="Plano FREE não permite ingestão automática.")

    _enforce_product_limit(db, user)

    headers = {"User-Agent": "Mozilla/5.0"}
    with httpx.Client(follow_redirects=True, timeout=6.0) as client:
        resp = client.get(payload.ml_url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Link inválido ou indisponível.")

    html = resp.text
    title_match = re.search(r"<title>(.*?)</title>", html, re.I)
    price_match = re.search(r"R\$[\s]*([\d.,]+)", html)
    image_match = re.search(r'content="(https://http2\.mlstatic\.com/[^"]+)"', html)

    title = title_match.group(1).split("|")[0].strip() if title_match else "Produto ML"
    price = price_match.group(1) if price_match else ""
    image_url = image_match.group(1) if image_match else None

    product = models.BlackLinkProduct(
        owner_id=user.id,
        title=title,
        description=None,
        url=payload.ml_url,
        image_url=image_url,
        source_image_url=image_url,
        price=price if price else None,
        badge=f"R$ {price}" if price else None,
        cta_label="Ver oferta",
        is_featured=int(payload.featured or 0),
        is_active=1,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return {
        "status": "ok",
        "user": user.username,
        "plan": user.plan,
        "plan_status": user.plan_status,
        "product_id": product.id,
        "title": product.title,
        "price": price,
    }
