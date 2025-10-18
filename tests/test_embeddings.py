import asyncio
import os

import httpx
import pytest


async def _probe_dim() -> int:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "http://localhost:8000/embed",
            json={"url": "https://example.com", "title": "Example", "domain": "example.com"},
        )
        r.raise_for_status()
        data = r.json()
        return len(data["vector"])


@pytest.mark.skipif(os.getenv("PHISHRADAR_EMBED_TESTS") != "1", reason="Embed integration test disabled by default")
def test_embedding_length_and_latency():
    dim = asyncio.run(_probe_dim())
    assert dim > 100
