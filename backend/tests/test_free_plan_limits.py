from __future__ import annotations
from uuid import uuid4

def test_free_plan_product_limit(client):
    username = f"teste_free_auto_{uuid4().hex[:8]}"

    # cria usuário FREE
    resp = client.post("/blacklink/", json={
        "username": username,
        "display_name": "Teste Free Auto",
        "plan": "free"
    })
    assert resp.status_code in (200, 201)

    # cria 3 produtos (OK)
    for i in range(1, 4):
        r = client.post(f"/product/{username}", json={
            "title": f"Produto {i}",
            "description": None,
            "url": "https://mercadolivre.com.br/teste",
            "image_url": None,
            "price": None,
            "tag": None,
            "badge": None,
            "cta_label": "Ver oferta",
            "is_featured": 0,
            "is_active": 1,
        })
        assert r.status_code in (200, 201)

    # 4º produto (BLOQUEADO)
    r = client.post(f"/product/{username}", json={
        "title": "Produto 4",
        "description": None,
        "url": "https://mercadolivre.com.br/teste",
        "image_url": None,
        "price": None,
        "tag": None,
        "badge": None,
        "cta_label": "Ver oferta",
        "is_featured": 0,
        "is_active": 1,
    })
    assert r.status_code == 403


def test_free_plan_ingest_blocked(client):
    username = f"teste_free_auto_{uuid4().hex[:8]}"

    # cria usuário FREE
    resp = client.post("/blacklink/", json={
        "username": username,
        "display_name": "Teste Free Auto",
        "plan": "free"
    })
    assert resp.status_code in (200, 201)

    # ingest deve ser bloqueado no FREE
    r = client.post("/admin/ingest", json={
        "username": username,
        "ml_url": "https://mercadolivre.com.br/teste",
        "featured": 1
    })
    assert r.status_code == 403
