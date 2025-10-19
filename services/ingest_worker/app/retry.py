from __future__ import annotations

from typing import Iterable, Type

from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from .config import settings


def net_retry(
    max_attempts: int | None = None,
    *,
    initial: float | None = None,
    maximum: float | None = None,
    multiplier: float | None = None,  # kept for future use; tenacity jitter doesn't take multiplier directly
    retry_on: Iterable[Type[BaseException]] | None = None,
):
    """Retry decorator tuned for network I/O.

    Defaults are driven by settings: RETRY_MAX_ATTEMPTS, RETRY_INITIAL_DELAY, RETRY_MAX_DELAY.
    """
    attempts = int(max_attempts or settings.retry_max_attempts)
    init = float(initial or settings.retry_initial_delay)
    mx = float(maximum or settings.retry_max_delay)
    cond = retry_if_exception_type(tuple(retry_on) if retry_on else Exception)
    return retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=init, max=mx),
        retry=cond,
    )
