import asyncio

import httpx


async def _post(path: str, json: dict):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=json)


def test_dedup_vector_mismatch_returns_400():
    # Set expected dim on app state to avoid hitting Ollama/Qdrant
    from app.main import app

    app.state.embed_dim = 3  # type: ignore[attr-defined]
    resp = asyncio.run(
        _post(
            "/dedup",
            {
                "url": "https://example.com/x",
                "vector": [0.1, 0.2],  # wrong length (2 != 3)
                "payload": {"domain": "example.com", "title": "x", "ts": 0},
            },
        )
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "vector dimension mismatch"


def test_hooks_slack_invalid_signature_401():
    from app.main import app
    from app import slack as slack_mod
    import json as _json

    # Configure known secret
    slack_mod.settings.slack_signing_secret = "topsecret"  # type: ignore[attr-defined]

    payload = _json.dumps({"user": {"id": "U1"}, "actions": [{"value": _json.dumps({"action": "approve", "url": "https://x"})}]})
    transport = httpx.ASGITransport(app=app)
    async def _call():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Wrong signature on purpose
            headers = {"x-slack-signature": "v0=deadbeef", "x-slack-request-timestamp": "123"}
            return await client.post("/hooks/slack", data={"payload": payload}, headers=headers)

    resp = asyncio.run(_call())
    assert resp.status_code == 401
