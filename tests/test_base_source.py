import time
import pytest
from hotspot.sources.base import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_enforces_interval():
    rl = RateLimiter(rate=2.0)
    start = time.monotonic()
    await rl.acquire()
    await rl.acquire()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.9


@pytest.mark.asyncio
async def test_rate_limiter_first_call_immediate():
    rl = RateLimiter(rate=1.0)
    start = time.monotonic()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1
