from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.services.plan_manager import get_policy, normalize_plan, sync_user_plan

router = APIRouter(prefix="/product", tags=["Product"])


def _get_user_by_username(db: Session, username: str) -> models.BlackLinkUser:
    username = username.lower().strip()
    user = db.query(models.BlackLinkUser).filter(models.BlackLinkUser.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário BlackLink não encontrado.")
    return sync_user_plan(db, user)


def _get_product_by_id(db: Session, product_id: int) -> models.BlackLinkProduct:
    product = db.query(models.BlackLinkProduct).filter(models.BlackLinkProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return product


def _enforce_product_limit(db: Session, user: models.BlackLinkUser) -> None:
    plan = normalize_plan(user.plan)
    policy = get_policy(plan)
    limit = policy.product_limit
    if limit is None:
        return

    count = db.query(models.BlackLinkProduct).filter(models.BlackLinkProduct.owner_id == user.id).count()
    if count >= limit:
        raise HTTPException(status_code=403, detail=f"Limite de produtos do plano {plan.upper()} atingido ({limit}).")


@router.get("/{username}", response_model=List[schemas.ProductOut])
def list_products_for_user(username: str, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    return (
        db.query(models.BlackLinkProduct)
        .filter(models.BlackLinkProduct.owner_id == user.id)
        .order_by(models.BlackLinkProduct.id.desc())
        .all()
    )


@router.post("/{username}", response_model=schemas.ProductOut, status_code=201)
def create_product_for_user(username: str, product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, username)
    _enforce_product_limit(db, user)

    data = product_in.model_dump()
    product = models.BlackLinkProduct(owner_id=user.id, **data)

    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/edit/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, product_update: schemas.ProductUpdate, db: Session = Depends(get_db)):
    product = _get_product_by_id(db, product_id)

    data = product_update.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(product, field, value)

    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = _get_product_by_id(db, product_id)
    db.delete(product)
    db.commit()
    return None
