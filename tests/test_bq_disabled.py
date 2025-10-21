import pytest

from app import bq


def test_bq_write_receipts_disabled_raises():
    # With default env (no credentials), BQ writes should be disabled and raise
    with pytest.raises(RuntimeError):
        bq.write_receipts([{"model": "m", "tokens": 0, "ms": 1, "cost": 0.0}])

