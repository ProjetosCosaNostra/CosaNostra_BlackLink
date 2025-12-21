from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4


def test_expired_paid_plan_downgrades_to_free_and_blocks_ingest(client):
    username = f"teste_exp_{uuid4().hex[:8]}"

    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    r = client.post("/blacklink/", json={
        "username": username,
        "display_name": "Teste Expirado",
        "plan": "pro",
        "plan_status": "active",
        "plan_expires_at": past,
    })
    assert r.status_code in (200, 201)

    r2 = client.post("/admin/ingest", json={
        "username": username,
        "ml_url": "https://mercadolivre.com.br/teste",
        "featured": 1
    })
    assert r2.status_code == 403

    r3 = client.get(f"/blacklink/{username}")
    assert r3.status_code == 200
    data = r3.json()
    assert data["plan"] == "free"
    assert data["plan_status"] == "expired"
