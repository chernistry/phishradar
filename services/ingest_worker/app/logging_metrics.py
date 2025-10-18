from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest


app_startups_total = Counter(
    "phishradar_app_startups_total", "Total number of API app startups"
)
healthz_checks_total = Counter(
    "phishradar_healthz_checks_total", "Total number of /healthz checks"
)
readiness_gauge = Gauge(
    "phishradar_readiness", "Readiness status (1=ready, 0=not ready)"
)


def on_startup() -> None:
    app_startups_total.inc()
    readiness_gauge.set(1)


def on_shutdown() -> None:
    readiness_gauge.set(0)


def prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

