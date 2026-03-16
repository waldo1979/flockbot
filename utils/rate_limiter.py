import asyncio
import time


class TokenBucket:
    """Async token-bucket rate limiter."""

    def __init__(self, rate: float = 10, period: float = 60.0, reserve: int = 3) -> None:
        self.rate = rate
        self.period = period
        self.reserve = reserve
        self.tokens = float(rate)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.period))
        self._last_refill = now

    async def acquire(self, priority: str = "high") -> None:
        """Acquire a token. Low-priority callers wait until reserve tokens are
        available for high-priority callers (registrations, interactive lookups).
        """
        if priority == "low":
            floor = self.reserve
        elif priority == "medium":
            floor = self.reserve // 2
        else:
            floor = 0
        async with self._lock:
            self._refill()
            while self.tokens < 1 + floor:
                wait = (1 + floor - self.tokens) * (self.period / self.rate)
                await asyncio.sleep(wait)
                self._refill()
            self.tokens -= 1

    def update_from_headers(self, remaining: int | None, reset_ts: float | None) -> None:
        """Adjust bucket state from X-RateLimit-Remaining / X-RateLimit-Reset headers."""
        if remaining is not None:
            self.tokens = min(self.rate, float(remaining))
        if reset_ts is not None:
            self._last_refill = time.monotonic() - (reset_ts - time.time())
