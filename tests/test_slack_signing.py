import hmac
import hashlib

from app.slack import verify_signature


def test_verify_signature_roundtrip():
    # This test assumes default empty secret will fail verification
    ts = "1234567890"
    body = b"payload=%7B%7D"
    # With empty secret, expected signature is deterministic (hmac of data with empty key)
    digest = hmac.new(b"", f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8"), hashlib.sha256).hexdigest()
    sig = f"v0={digest}"
    ok = verify_signature(ts, sig, body)
    assert ok is True

