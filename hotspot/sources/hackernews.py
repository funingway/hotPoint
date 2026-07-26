import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API_URL = "https://hn.algolia.com/api/v1/search"


@register_source
class HackerNewsSource(BaseSource):
    name = "hackernews"

    def __init__(self, min_points: int = 10, rate_limit: float = 1.0, **_):
        self.min_points = min_points
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        now = int(datetime.now(timezone.utc).timestamp())
        min_ts = now - hours * 3600
        params = {
            "query": topic,
            "tags": "story",
            "numericFilters": f"created_at_i>{min_ts},points>={self.min_points}",
            "hitsPerPage": 50,
        }
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        items = []
        now_dt = datetime.now(timezone.utc)
        for hit in data.get("hits", []):
            if hit.get("points", 0) < self.min_points:
                continue
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            items.append(Item(
                source=self.name,
                source_type=SourceType.news,
                external_id=str(hit["objectID"]),
                title=hit.get("title") or "(no title)",
                url=url,
                author=hit.get("author"),
                published_at=datetime.fromtimestamp(
                    hit.get("created_at_i", now), tz=timezone.utc
                ),
                fetched_at=now_dt,
                raw_content=hit.get("story_text") or hit.get("title") or "",
                metrics={
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                },
                language="en",
            ))
        return items
