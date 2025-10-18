from __future__ import annotations

import hashlib
import json
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
    dedup_requests_total,
    dedup_duplicates_total,
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
        app.state.embed_dim = dim  # type: ignore[attr-defined]
        # Ensure Qdrant collection and payload indexes
        try:
            from .qdrant_client import QdrantStore

            store = QdrantStore()
            await store.ensure_collection(dim)
            await store.ensure_payload_indexes()
        except Exception as qe:
            logging.getLogger(__name__).warning(f"Qdrant ensure failed: {qe}")
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
from fastapi import Body, HTTPException, Header, Form  # noqa: E402
from .models import (
    EmbedIn,
    EmbedOut,
    DedupIn,
    DedupOut,
    SlackNotifyIn,
    UrlItem,
    EnrichIn,
    EnrichOut,
)  # noqa: E402
from .embeddings import OllamaEmbeddings  # noqa: E402
from .dedup import upsert_and_check  # noqa: E402
from .slack import send_message, verify_signature, action_blocks, respond  # noqa: E402
from .logging_metrics import slack_messages_sent_total, slack_webhooks_total, slack_webhooks_invalid_total  # noqa: E402


@app.post("/embed", response_model=EmbedOut)
async def embed(payload: EmbedIn = Body(...)) -> EmbedOut:
    emb = OllamaEmbeddings()
    vector, ms, model = await emb.embed_async_single(
        f"{payload.url} | {payload.title} | {payload.domain}"
    )
    return EmbedOut(vector=vector, model=model, ms=ms)


@app.post("/dedup", response_model=DedupOut)
async def dedup(body: DedupIn) -> DedupOut:
    dedup_requests_total.inc()
    if not body.vector:
        raise HTTPException(status_code=400, detail="empty vector")
    # Validate dimension if known
    embed_dim = getattr(app.state, "embed_dim", None)  # type: ignore[attr-defined]
    if embed_dim is not None and len(body.vector) != int(embed_dim):
        raise HTTPException(status_code=400, detail="vector dimension mismatch")
    dup, sim, qid = await upsert_and_check(str(body.url), body.vector, body.payload)
    if dup:
        dedup_duplicates_total.inc()
    return DedupOut(is_duplicate=dup, similarity=sim, qdrant_id=qid)


@app.post("/ingest/fetch")
async def ingest_fetch() -> list[UrlItem]:
    # Minimal stub to allow n8n flow execution; future ticket can fetch real feeds
    now_iso = "1970-01-01T00:00:00Z"
    return [
        UrlItem(url="https://example.com/phish", domain="example.com", ts=now_iso),
    ]


@app.post("/enrich", response_model=EnrichOut)
async def enrich(body: EnrichIn) -> EnrichOut:
    # Minimal safe enrichment without external fetch
    from urllib.parse import urlparse

    parsed = urlparse(str(body.url))
    title = parsed.netloc or ""
    return EnrichOut(url=body.url, title=title, snapshot_hash=None)


@app.post("/log")
async def log_event(payload: dict = Body(...)) -> dict[str, bool]:  # type: ignore[type-arg]
    # Append to local buffer JSONL (will be consumed in Ticket 7)
    import os
    import json as _json

    buf_dir = os.path.join(os.getcwd(), "buffer")
    os.makedirs(buf_dir, exist_ok=True)
    path = os.path.join(buf_dir, "events.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # best-effort; surface ok anyway to not break flow
        pass
    return {"ok": True}


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
@app.post("/notify/slack")
async def notify_slack(body: SlackNotifyIn):
    blocks = action_blocks(str(body.url), body.title, body.similarity)
    data = await send_message(text=f"New phishing alert: {body.title}", blocks=blocks)
    slack_messages_sent_total.inc()
    return {"ok": True, "ts": data.get("ts"), "channel": data.get("channel")}


@app.post("/hooks/slack")
async def hooks_slack(
    x_slack_signature: str = Header(""),
    x_slack_request_timestamp: str = Header(""),
    payload: str = Form(""),
):
    slack_webhooks_total.inc()
    body = f"payload={payload}".encode("utf-8")
    if not verify_signature(x_slack_request_timestamp, x_slack_signature, body):
        slack_webhooks_invalid_total.inc()
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")
    # Quick ack via response_url if provided
    resp_url = event.get("response_url")
    if resp_url:
        try:
            await respond(resp_url, "Thanks. Action received.")
        except Exception:
            pass
    action = (event.get("actions") or [{}])[0]
    action_val = action.get("value")
    try:
        parsed = json.loads(action_val) if action_val else {}
    except Exception:
        parsed = {"action": "unknown"}
    user = (event.get("user") or {}).get("username") or (event.get("user") or {}).get("id")
    # TODO(T7): persist to BQ
    return {"ok": True, "user": user, "action": parsed}
