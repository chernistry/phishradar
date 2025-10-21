import sys
import types

from app import bq as bqmod


def _install_fake_bigquery(monkeypatch):
    # Create fake google.cloud.bigquery with minimal Client
    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    bigquery = types.ModuleType("google.cloud.bigquery")

    class Client:
        def __init__(self, project):
            self.project = project

        def insert_rows_json(self, table_id, rows):
            # Return [] to indicate success
            return []

    bigquery.Client = Client
    cloud.bigquery = bigquery
    google.cloud = cloud
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)


def test_bq_write_receipts_and_events_success(monkeypatch):
    # Force enabled
    monkeypatch.setattr(bqmod.settings, "gcp_project_id", "proj")
    monkeypatch.setattr(bqmod.settings, "google_app_credentials", "/tmp/creds.json")
    _install_fake_bigquery(monkeypatch)

    # Should not raise
    bqmod.write_receipts([{"model": "m", "tokens": 0, "ms": 1, "cost": 0.0}])
    bqmod.write_events([{"a": 1}])

