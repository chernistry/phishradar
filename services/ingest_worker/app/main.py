from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Response

from .config import get_settings
from .logging_metrics import on_shutdown, on_startup, prometheus_metrics, healthz_checks_total


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    on_startup()
    try:
        yield
    finally:
        on_shutdown()


app = FastAPI(title="PhishRadar Ingest Worker", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    healthz_checks_total.inc()
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    content, content_type = prometheus_metrics()
    return Response(content=content, media_type=content_type)


def main() -> None:
    settings = get_settings()
    host = settings.api_host
    port = settings.api_port
    # Allow overriding via Uvicorn's env if present
    host = os.getenv("HOST", host)
    port = int(os.getenv("PORT", str(port)))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
        factory=False,
    )


if __name__ == "__main__":
    main()

