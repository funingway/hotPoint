import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from hotspot.models import Item


class RateLimiter:
    def __init__(self, rate: float = 1.0):
        self._interval = 1.0 / rate if rate > 0 else 0
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last is not None:
                wait = self._interval - (now - self._last)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
            self._last = now


class BaseSource(ABC):
    name: str

    @abstractmethod
    async def fetch(self, topic: str, hours: int) -> list[Item]:
        ...

    async def fetch_full(self, item: Item) -> str:
        return item.raw_content

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)
