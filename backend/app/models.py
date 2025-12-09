from sqlalchemy import Column, Integer, String, DateTime, func, UniqueConstraint
from .database import Base


class BlackLink(Base):
    __tablename__ = "blacklinks"
    __table_args__ = (UniqueConstraint("username", name="uq_blacklinks_username"),)

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, index=True)
    theme = Column(String(20), nullable=False, default="corleone")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProductOfTheDay(Base):
    __tablename__ = "product_of_the_day"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    price = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)
    link = Column(String(500), nullable=False)
