from __future__ import annotations

import contextvars
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


# Prometheus custom registry and metrics
registry = CollectorRegistry()
req_counter = Counter(
    "phishradar_requests_total",
    "Total requests",
    ["path", "method", "status"],
    registry=registry,
)
latency_hist = Histogram(
    "phishradar_latency_seconds",
    "Latency by path",
    ["path"],
    registry=registry,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

dedup_requests_total = Counter(
    "phishradar_dedup_requests_total", "Total dedup requests", registry=registry
)
dedup_duplicates_total = Counter(
    "phishradar_dedup_duplicates_total", "Total duplicates detected", registry=registry
)

slack_messages_sent_total = Counter(
    "phishradar_slack_messages_sent_total", "Slack messages sent", registry=registry
)
slack_webhooks_total = Counter(
    "phishradar_slack_webhooks_total", "Slack webhooks received", registry=registry
)
slack_webhooks_invalid_total = Counter(
    "phishradar_slack_webhooks_invalid_total", "Slack webhooks rejected (invalid)", registry=registry
)

# Readiness gauge for health reporting
from prometheus_client import Gauge  # noqa: E402

readiness_gauge = Gauge(
    "phishradar_readiness", "Readiness status (1=ready, 0=not ready)", registry=registry
)


def set_ready() -> None:
    readiness_gauge.set(1)


def set_unready() -> None:
    readiness_gauge.set(0)


# Correlation id context
correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(level)


# Metrics router
metrics_router = APIRouter()


@metrics_router.get("/metrics")
def metrics() -> Response:
    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
