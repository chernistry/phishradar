from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential_jitter


def net_retry(max_attempts: int = 5):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=0.25, max=5),
    )
