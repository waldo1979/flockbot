import asyncio
import time

import pytest

from utils.rate_limiter import TokenBucket


class TestTokenBucket:
    async def test_initial_tokens_available(self):
        bucket = TokenBucket(rate=10, period=60.0)
        # Should be able to acquire 10 times immediately
        for _ in range(10):
            await bucket.acquire()

    async def test_blocks_when_empty(self):
        bucket = TokenBucket(rate=2, period=1.0)
        await bucket.acquire()
        await bucket.acquire()
        # Third acquire should block
        start = time.monotonic()
        await bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3  # Should have waited ~0.5s

    async def test_update_from_headers(self):
        bucket = TokenBucket(rate=10, period=60.0)
        # Drain all tokens
        for _ in range(10):
            await bucket.acquire()
        # Simulate server saying 5 remaining
        bucket.update_from_headers(remaining=5, reset_ts=None)
        assert bucket.tokens == 5.0
