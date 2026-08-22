"""Retry with exponential backoff for outbound HTTP calls.

No external dependency: tenacity is intentionally avoided so the pipeline
stays installable offline. Retries only transient failures (transport errors
and 5xx); 4xx responses are returned as-is.
"""

import random
import time
from collections.abc import Callable

from app.config import HTTP_RETRY_ATTEMPTS, HTTP_RETRY_BASE_DELAY

RETRYABLE_STATUS = {500, 502, 503, 504, 429}


def call_with_retry(
    fn: Callable[[], tuple[int, str, str]],
    attempts: int | None = None,
    base_delay: float | None = None,
) -> tuple[int, str, str]:
    max_attempts = attempts or HTTP_RETRY_ATTEMPTS
    delay = base_delay if base_delay is not None else HTTP_RETRY_BASE_DELAY
    last: tuple[int, str, str] = (0, "", "")
    for attempt in range(max_attempts):
        try:
            status, html, final_url = fn()
        except Exception:
            status, html, final_url = 0, "", ""
        if html and status < 400:
            return status, html, final_url
        last = (status, html, final_url)
        if status and status not in RETRYABLE_STATUS and attempt < max_attempts - 1:
            break
        if attempt < max_attempts - 1:
            time.sleep(delay * (2**attempt) * (0.5 + random.random()))
    return last
