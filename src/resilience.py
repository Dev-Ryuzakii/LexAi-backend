"""
Retry and failure-isolation helpers.

- retry_call: exponential backoff with "full jitter" (sleep a random time between 0 and
  the capped exponential delay), which spreads out retries from many clients so they do
  not hit a recovering service at the same moment.
- CircuitBreaker: after `failure_threshold` consecutive failures, calls are skipped for
  `reset_timeout` seconds; one trial call is then let through ("half-open"). This stops
  every request from waiting on a provider that is known to be down.
"""
import logging
import random
import threading
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
    """Full-jitter delay for retry number `attempt` (1-based)."""
    return random.uniform(0, min(cap, base * (2 ** (attempt - 1))))


def retry_call(
    fn: Callable[[], T],
    attempts: int = 3,
    base: float = 0.5,
    cap: float = 30.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    should_retry: Optional[Callable[[BaseException], bool]] = None,
    sleep: Optional[Callable[[float], None]] = None,
    label: str = 'operation',
) -> T:
    """Call `fn`, retrying failures in `retry_on` with jittered exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as e:
            if attempt == attempts or (should_retry is not None and not should_retry(e)):
                raise
            delay = backoff_delay(attempt, base, cap)
            logger.warning(f"{label} failed (attempt {attempt}/{attempts}): {e}; retrying in {delay:.2f}s")
            (sleep or time.sleep)(delay)
    raise RuntimeError('unreachable')


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return 'closed'
            if time.monotonic() - self._opened_at >= self.reset_timeout:
                return 'half_open'
            return 'open'

    def allow(self) -> bool:
        return self.state != 'open'

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                if self._opened_at is None:
                    logger.error(f"Circuit for {self.name} opened after {self._failures} consecutive failures")
                self._opened_at = time.monotonic()

    def call(self, fn: Callable[[], T]) -> T:
        if not self.allow():
            raise CircuitOpenError(f"{self.name} is temporarily disabled after repeated failures")
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result
