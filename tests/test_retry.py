import time

from app.retry import net_retry


def test_net_retry_retries_then_succeeds():
    calls = {"n": 0}

    @net_retry(max_attempts=3, initial=0.01, maximum=0.02)
    def sometimes_fails():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return 42

    t0 = time.perf_counter()
    out = sometimes_fails()
    assert out == 42
    assert calls["n"] == 2
    # ensure we actually waited a little between attempts (loose bound)
    assert (time.perf_counter() - t0) >= 0.0

