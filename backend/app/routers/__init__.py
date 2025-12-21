"""
app.routers package

⚠️ Não importe submódulos aqui.

Motivo:
- Importar routers dentro do __init__.py pode causar ImportError em cascata
  (ex: quando um router importa models que ainda não carregaram corretamente),
  e derruba o container no startup (Railway/Uvicorn).
"""
