import asyncio

import httpx


async def _get(path: str) -> httpx.Response:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_healthz_ok():
    resp = asyncio.run(_get("/healthz"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_metrics_exposed():
    resp = asyncio.run(_get("/metrics"))
    assert resp.status_code == 200
    body = resp.text
    assert "phishradar_requests_total" in body
    assert "phishradar_readiness" in body

