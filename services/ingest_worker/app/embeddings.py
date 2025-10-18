from __future__ import annotations

import time
from typing import Any

import httpx

from .config import settings
from .retry import net_retry


class EmbeddingError(Exception):
    pass


class OllamaEmbeddings:
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 15.0):
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.embed_model_name
        self.timeout = timeout
        self._dim: int | None = None

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()

    @net_retry()
    async def embed_async_single(self, text: str) -> tuple[list[float], int, str]:
        start = time.perf_counter()
        try:
            # Ollama embeddings API expects "prompt" (not "input").
            data = {"model": self.model, "prompt": text}
            out = await self._post("/api/embeddings", data)
            vector = out.get("embedding") or (out.get("data", [{}])[0] or {}).get("embedding")
            if not isinstance(vector, list):
                raise EmbeddingError("Invalid embedding response shape")
            ms = int((time.perf_counter() - start) * 1000)
            return vector, ms, self.model
        except httpx.HTTPError as e:
            raise EmbeddingError(str(e))

    async def dim(self) -> int:
        if self._dim is not None:
            return self._dim
        vector, _, _ = await self.embed_async_single("dimension probe")
        self._dim = len(vector)
        return self._dim
