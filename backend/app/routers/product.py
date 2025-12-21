from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import Product, User
from app.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductOut,
)

router = APIRouter(
    prefix="/product",
    tags=["Product"]
)

# ============================================================
# LIMITES DE PRODUTOS POR PLANO
# ============================================================
PLAN_PRODUCT_LIMITS = {
    "free": 3,
    "pro": 20,
    "don": None,  # ilimitado
}


def check_product_limit(user: User, db: Session):
    plan = (user.plan or "free").lower()
    limit = PLAN_PRODUCT_LIMITS.get(plan, 3)

    # DON = ilimitado
    if limit is None:
        return

    total_products = (
        db.query(Product)
        .filter(Product.owner_id == user.id)
        .count()
    )

    if total_products >= limit:
        # 🎯 MENSAGEM DE UPGRADE
        if plan == "free":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "product_limit_reached",
                    "message": (
                        "Você atingiu o limite de 3 produtos do plano FREE. "
                        "Faça upgrade para o plano PRO e libere até 20 produtos."
                    ),
                    "current_plan": "FREE",
                    "suggested_plan": "PRO",
                    "upgrade_required": True
                }
            )

        # fallback (PRO atingiu limite)
        raise HTTPException(
            status_code=403,
            detail=f"Limite de produtos atingido para o plano {plan.upper()} ({limit})"
        )


# ============================================================
# GET /product/{username}
# Lista produtos do usuário
# ============================================================
@router.get("/{username}", response_model=List[ProductOut])
def list_products_for_user(
    username: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    products = (
        db.query(Product)
        .filter(Product.owner_id == user.id)
        .order_by(Product.id.desc())
        .all()
    )

    return products


# ============================================================
# POST /product/{username}
# Cria produto (COM BLOQUEIO + MENSAGEM DE UPGRADE)
# ============================================================
@router.post("/{username}", response_model=ProductOut, status_code=201)
def create_product_for_user(
    username: str,
    payload: ProductCreate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔒 BLOQUEIO POR PLANO (com mensagem de upgrade)
    check_product_limit(user, db)

    product = Product(
        owner_id=user.id,
        **payload.model_dump()
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


# ============================================================
# PATCH /product/edit/{product_id}
# Atualiza produto
# ============================================================
@router.patch("/edit/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    data = payload.model_dump(exclude_unset=True)

    for field, value in data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


# ============================================================
# DELETE /product/{product_id}
# Deleta produto
# ============================================================
@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return None
