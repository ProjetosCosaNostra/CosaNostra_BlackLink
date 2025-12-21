from __future__ import annotations

import re
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import TEMPLATES_DIR
from ..database import get_db
from .. import models

router = APIRouter(tags=["Catalog"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# Helpers — User (AUTO-CREATE SAAS)
# ============================================================

def _get_or_create_user(db: Session, username: str) -> models.BlackLinkUser:
    username = (username or "").lower().strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username inválido.")

    user = (
        db.query(models.BlackLinkUser)
        .filter(models.BlackLinkUser.username == username)
        .first()
    )

    if not user:
        user = models.BlackLinkUser(
            username=username,
            display_name=username,
            plan="free",
            bio="Loja BlackLink"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


# ============================================================
# Helpers — Products
# ============================================================

def _parse_price_from_badge(badge: Optional[str]) -> str:
    if not badge:
        return ""

    s = badge.strip()
    m = re.search(
        r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)",
        s,
    )
    if not m:
        return ""

    return m.group(1).replace(" ", "")


def _safe_image_url(product: models.BlackLinkProduct) -> str:
    url = getattr(product, "source_image_url", None)
    if url:
        return url
    return "/assets/CosaNostraAI.ico"


def _is_link_alive(url: str) -> bool:
    if not url:
        return False

    if "mercadolivre.com" not in url and "mercadolivre.com.br" not in url:
        return True

    try:
        with httpx.Client(follow_redirects=True, timeout=3.0) as client:
            resp = client.head(url)
            if resp.status_code == 405:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})

        if resp.status_code in (404, 410):
            return False

        if resp.history and resp.status_code in (404, 410):
            return False

        return True

    except httpx.RequestError:
        return True


def _base_queryset_products(
    db: Session,
    owner_id: int,
    q: Optional[str],
    order_by: str,
    direction: str,
):
    query = db.query(models.BlackLinkProduct).filter(
        models.BlackLinkProduct.owner_id == owner_id
    )

    if q:
        query = query.filter(models.BlackLinkProduct.title.ilike(f"%{q}%"))

    if order_by == "title":
        sort_field = models.BlackLinkProduct.title
    elif order_by == "badge":
        sort_field = models.BlackLinkProduct.badge
    else:
        sort_field = models.BlackLinkProduct.id

    if direction == "desc":
        sort_field = sort_field.desc()

    return query.order_by(sort_field)


def _product_to_viewmodel(product: models.BlackLinkProduct) -> dict:
    return {
        "id": product.id,
        "name": product.title,
        "price": _parse_price_from_badge(product.badge),
        "image_url": _safe_image_url(product),
        "link": product.url or "",
    }


# ============================================================
# LOJA PÚBLICA
# /blacklink/{username}/produtos
# ============================================================

@router.get(
    "/blacklink/{username}/produtos",
    response_class=HTMLResponse,
    name="user_products",
)
def user_products_page(
    username: str,
    request: Request,
    q: Optional[str] = Query(default=None),
    order_by: str = Query(default="id", pattern="^(id|title|badge)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    user = _get_or_create_user(db, username)

    products_db: List[models.BlackLinkProduct] = (
        _base_queryset_products(db, user.id, q, order_by, direction).all()
    )

    alive_products = [p for p in products_db if _is_link_alive(p.url or "")]
    products_vm = [_product_to_viewmodel(p) for p in alive_products]

    context = {
        "request": request,
        "username": user.username,
        "products": products_vm,
        "q": q or "",
        "order_by": order_by,
        "direction": direction,
    }
    return templates.TemplateResponse("user_products.html", context)


# ============================================================
# DETALHE DO PRODUTO
# /blacklink/{username}/produto/{product_id}
# ============================================================

@router.get(
    "/blacklink/{username}/produto/{product_id}",
    response_class=HTMLResponse,
    name="user_product_detail",
)
def product_detail_page(
    username: str,
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_or_create_user(db, username)

    product = (
        db.query(models.BlackLinkProduct)
        .filter(models.BlackLinkProduct.id == product_id)
        .first()
    )

    if not product or product.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")

    if not _is_link_alive(product.url or ""):
        raise HTTPException(status_code=404, detail="Produto indisponível.")

    product_vm = _product_to_viewmodel(product)

    others_db = (
        db.query(models.BlackLinkProduct)
        .filter(
            models.BlackLinkProduct.owner_id == user.id,
            models.BlackLinkProduct.id != product_id,
        )
        .order_by(models.BlackLinkProduct.id.desc())
        .all()
    )

    others_vm = [
        _product_to_viewmodel(p)
        for p in others_db
        if _is_link_alive(p.url or "")
    ][:3]

    context = {
        "request": request,
        "username": user.username,
        "product": product_vm,
        "others": others_vm,
    }
    return templates.TemplateResponse("product_detail.html", context)


# ============================================================
# REDIRECT DE AFILIADO
# /blacklink/out/{product_id}
# ============================================================

@router.get(
    "/blacklink/out/{product_id}",
    response_class=RedirectResponse,
    name="product_out",
)
def product_out(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(models.BlackLinkProduct)
        .filter(models.BlackLinkProduct.id == product_id)
        .first()
    )

    if not product or not _is_link_alive(product.url or ""):
        raise HTTPException(status_code=404, detail="Produto indisponível.")

    return RedirectResponse(url=product.url)


# ============================================================
# API JSON (opcional)
# ============================================================

@router.get("/api/blacklink/{username}/products", response_class=JSONResponse)
def api_list_user_products(username: str, db: Session = Depends(get_db)):
    user = _get_or_create_user(db, username)

    products = (
        db.query(models.BlackLinkProduct)
        .filter(models.BlackLinkProduct.owner_id == user.id)
        .order_by(models.BlackLinkProduct.id.desc())
        .all()
    )

    return JSONResponse(
        content=[
            {
                "id": p.id,
                "owner_id": p.owner_id,
                "title": p.title,
                "description": p.description,
                "url": p.url,
                "tag": p.tag,
                "badge": p.badge,
                "cta_label": p.cta_label,
            }
            for p in products
        ]
    )
