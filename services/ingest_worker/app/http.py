from __future__ import annotations

import httpx


def async_http_client(timeout: float = 10.0, max_connections: int = 20, max_keepalive: int = 10) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with sane limits for our workloads."""
    limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_keepalive)
    return httpx.AsyncClient(timeout=timeout, limits=limits)

