from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from . import models
from .routers import blacklinks, product

# Cria tabelas no SQLite
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CosaNostra BlackLink API")

# CORS – libera chamadas do front (ajuste depois se quiser restringir)
origins = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:5500",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas da API
app.include_router(blacklinks.router)
app.include_router(product.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "BlackLink API rodando"}
