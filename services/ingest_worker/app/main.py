from __future__ import annotations

import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from .config import settings
from .logging_metrics import (
    correlation_id,
    latency_hist,
    metrics_router,
    req_counter,
    setup_logging,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    # OTel instrumentation (safe if exporter unset)
    try:
        FastAPIInstrumentor.instrument_app(app)  # type: ignore[name-defined]
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        logging.getLogger(__name__).warning(f"OTel instrumentation failed: {e}")
    # Probe embeddings dimension (warm-up Ollama)
    try:
        from .embeddings import OllamaEmbeddings

        emb = OllamaEmbeddings()
        dim = await emb.dim()
        logging.getLogger(__name__).info(f"EMBED_DIM={dim} (model={emb.model})")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Embedding probe failed: {e}")
    yield


app = FastAPI(title="PhishRadar Ingest Worker", version="0.1.0", lifespan=lifespan)
app.include_router(metrics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_mw(request: Request, call_next):  # type: ignore[no-untyped-def]
    url = str(request.url)
    cid = hashlib.sha256(url.encode()).hexdigest()[:16]
    token = correlation_id.set(cid)
    try:
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response
    finally:
        correlation_id.reset(token)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(getattr(response, "status_code", 500))
        return response
    finally:
        elapsed = time.perf_counter() - start
        path = request.url.path
        try:
            latency_hist.labels(path=path).observe(elapsed)
            req_counter.labels(path=path, method=request.method, status=status).inc()
        except Exception:
            pass


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):  # type: ignore[no-untyped-def]
    logging.getLogger(__name__).exception("Unhandled error")
    return JSONResponse({"code": "ERR_UNKNOWN", "message": str(exc)}, status_code=500)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}

# Embeddings endpoint (Ticket 3)
from fastapi import Body  # noqa: E402
from .models import EmbedIn, EmbedOut  # noqa: E402
from .embeddings import OllamaEmbeddings  # noqa: E402


@app.post("/embed", response_model=EmbedOut)
async def embed(payload: EmbedIn = Body(...)) -> EmbedOut:
    emb = OllamaEmbeddings()
    vector, ms, model = await emb.embed_async_single(
        f"{payload.url} | {payload.title} | {payload.domain}"
    )
    return EmbedOut(vector=vector, model=model, ms=ms)


def main() -> None:
    host = os.getenv("HOST", settings.api_host)
    port = int(os.getenv("PORT", str(settings.api_port)))
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
