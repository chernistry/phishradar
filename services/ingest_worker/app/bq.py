from __future__ import annotations

import time
from typing import Any

from anyio import to_thread

from .config import settings
from .logging_metrics import bq_writes_total, bq_failures_total, bq_latency_seconds
from .dlq import write_dlq


def _enabled() -> bool:
    return (settings.google_app_credentials or "") != "" and (settings.gcp_project_id or "") != ""


def _insert_rows_sync(table: str, rows: list[dict[str, Any]]) -> None:
    """Synchronous BigQuery insert - should only be called from thread pool."""
    if not _enabled():
        raise RuntimeError("bq_disabled")
    try:
        from google.cloud import bigquery  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("bq_client_missing") from e
    client = bigquery.Client(project=settings.gcp_project_id)
    dataset = settings.bq_dataset
    table_id = f"{client.project}.{dataset}.{table}"
    errors = client.insert_rows_json(table_id, rows)
    if errors:  # pragma: no cover
        raise RuntimeError(str(errors))


async def write_events(rows: list[dict[str, Any]]) -> None:
    """Async wrapper for BigQuery events write."""
    table = "events"
    t0 = time.perf_counter()
    bq_writes_total.labels(table=table).inc()
    try:
        # Run blocking BigQuery call in thread pool
        await to_thread.run_sync(_insert_rows_sync, table, rows)
    except Exception as e:
        bq_failures_total.labels(table=table).inc()
        for r in rows:
            write_dlq("bq_write_events", r, str(e))
        raise
    finally:
        bq_latency_seconds.labels(table=table).observe(time.perf_counter() - t0)


async def write_receipts(rows: list[dict[str, Any]]) -> None:
    """Async wrapper for BigQuery receipts write."""
    table = "receipts"
    t0 = time.perf_counter()
    bq_writes_total.labels(table=table).inc()
    try:
        # Run blocking BigQuery call in thread pool
        await to_thread.run_sync(_insert_rows_sync, table, rows)
    except Exception as e:
        bq_failures_total.labels(table=table).inc()
        for r in rows:
            write_dlq("bq_write_receipts", r, str(e))
        raise
    finally:
        bq_latency_seconds.labels(table=table).observe(time.perf_counter() - t0)

