from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/api/product-of-the-day",
    tags=["product_of_the_day"]
)


def _get_singleton_product(db: Session) -> models.ProductOfTheDay:
    product = db.query(models.ProductOfTheDay).first()
    if not product:
        # cria um produto padrão (Basike) se não existir nenhum
        product = models.ProductOfTheDay(
            name="Fone Basike IPX5 — 100h bateria",
            price="R$ 86,33",
            image_url="https://http2.mlstatic.com/D_NQ_NP_740798-MLU78733917522_092024-O.webp",
            link="https://mercadolivre.com/sec/1UaiCb1",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
    return product


@router.get("/", response_model=schemas.ProductOut)
def get_product_of_the_day(db: Session = Depends(get_db)):
    product = _get_singleton_product(db)
    return product


@router.put("/", response_model=schemas.ProductOut)
def update_product_of_the_day(payload: schemas.ProductBase, db: Session = Depends(get_db)):
    product = _get_singleton_product(db)

    product.name = payload.name
    product.price = payload.price
    product.image_url = payload.image_url
    product.link = payload.link

    db.add(product)
    db.commit()
    db.refresh(product)
    return product
