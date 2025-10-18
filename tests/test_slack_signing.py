import hashlib
import hmac
import time

from app import slack


def test_verify_signature_roundtrip_and_freshness():
    # Set a known secret
    slack.settings.slack_signing_secret = "topsecret"  # type: ignore[attr-defined]
    now = int(time.time())
    ts = str(now)
    body = b"payload=%7B%7D"
    digest = hmac.new(b"topsecret", f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8"), hashlib.sha256).hexdigest()
    sig = f"v0={digest}"
    assert slack.verify_signature(ts, sig, body) is True

    # Stale timestamp should be rejected
    old_ts = str(now - 4000)
    old_sig = f"v0={hmac.new(b'topsecret', f'v0:{old_ts}:{body.decode('utf-8')}'.encode('utf-8'), hashlib.sha256).hexdigest()}"
    assert slack.verify_signature(old_ts, old_sig, body) is False
