from pydantic import BaseModel, constr
from typing import Optional


class BlackLinkCreate(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=30)
    theme: str = "corleone"


class BlackLinkOut(BaseModel):
    username: str
    theme: str
    url_path: str

    class Config:
        orm_mode = True


class ProductBase(BaseModel):
    name: str
    price: Optional[str] = None
    image_url: Optional[str] = None
    link: str


class ProductOut(ProductBase):
    id: int

    class Config:
        orm_mode = True
