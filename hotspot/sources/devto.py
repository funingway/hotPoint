import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API = "https://dev.to/api/articles"


@register_source
class DevtoSource(BaseSource):
    name = "devto"

    def __init__(self, min_reactions: int = 50, rate_limit: float = 1.0, **_):
        self.min_reactions = min_reactions
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        params = {"tag": topic, "per_page": 50}
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API, params=params)
            resp.raise_for_status()
            data = resp.json()
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        items = []
        for a in data:
            reactions = a.get("positive_reactions_count", 0)
            if reactions < self.min_reactions:
                continue
            try:
                pub = datetime.fromisoformat(a.get("published_at", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub.timestamp() < cutoff:
                continue
            items.append(Item(
                source=self.name,
                source_type=SourceType.blog,
                external_id=str(a.get("id", "")),
                title=a.get("title", ""),
                url=a.get("url", ""),
                author=(a.get("user") or {}).get("username"),
                published_at=pub,
                fetched_at=now,
                raw_content=a.get("description") or "",
                metrics={"reactions": reactions, "comments": a.get("comments_count", 0)},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        ext_id = item.external_id
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(f"{API}/{ext_id}")
                if resp.status_code != 200:
                    return item.raw_content
                body = resp.json().get("body_markdown") or item.raw_content
            except httpx.HTTPError:
                return item.raw_content
        return body[:10000]
