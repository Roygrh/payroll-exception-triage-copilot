"""Client-side pacing and retry with backoff for rate-limited free tiers (ADR-016).

`Pacer` spaces calls so that at most `rpm` requests start per minute (a simple
minimum interval between call starts). `call_with_retries` retries retryable
errors (HTTP 429, 5xx, transport errors) with exponential backoff and jitter,
honoring a `retry-after` value when the provider sends one.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from payroll_triage.llm.v1.interface import LLMError

RATE_LIMIT_HEADERS = (
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
)


class Pacer:
    def __init__(self, rpm: int, sleep: Callable[[float], None] = time.sleep) -> None:
        self.min_interval = 60.0 / rpm if rpm > 0 else 0.0
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_start = 0.0

    def wait(self) -> float:
        """Block until the next call may start; returns the seconds waited."""
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._last_start + self.min_interval - now)
            if delay > 0:
                self._sleep(delay)
            self._last_start = time.monotonic()
        return delay


def backoff_delay(attempt: int, base: float, cap: float, retry_after: float | None) -> float:
    """Delay before retry number `attempt` (1-based)."""
    if retry_after is not None and retry_after > 0:
        return min(cap, retry_after + random.uniform(0.0, 0.5))
    return min(cap, base * (2 ** (attempt - 1)) + random.uniform(0.0, base))


def call_with_retries[T](
    fn: Callable[[], T],
    *,
    max_attempts: int,
    base_delay: float = 1.0,
    cap: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Run `fn`; retry on retryable LLMError. Returns (result, attempts used)."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn(), attempt
        except LLMError as exc:
            if not exc.retryable or attempt >= max_attempts:
                raise
            sleep(backoff_delay(attempt, base_delay, cap, exc.retry_after))


def extract_rate_limit(headers) -> dict[str, str]:
    """Snapshot of the provider's rate limit headers (never includes credentials)."""
    out: dict[str, str] = {}
    for name in RATE_LIMIT_HEADERS:
        value = headers.get(name)
        if value is not None:
            out[name] = str(value)
    return out


def parse_retry_after(headers) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
