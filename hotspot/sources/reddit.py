import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

BASE = "https://www.reddit.com"


@register_source
class RedditSource(BaseSource):
    name = "reddit"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 20,
        rate_limit: float = 1.0,
        **_,
    ):
        self.subreddits = subreddits or ["programming", "MachineLearning", "technology", "artificial"]
        self.min_score = min_score
        self._limiter = RateLimiter(rate_limit)

    async def _search_sub(self, client: httpx.AsyncClient, sub: str, topic: str, hours: int) -> list[Item]:
        params = {
            "q": topic, "sort": "new", "limit": 25,
            "t": "day" if hours <= 24 else "week",
            "restrict_sr": "on",
        }
        await self._limiter.acquire()
        try:
            resp = await client.get(f"{BASE}/r/{sub}/search.json", params=params)
            if resp.status_code == 429:
                return []
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = resp.json().get("data", {}).get("children", [])
        now = datetime.now(timezone.utc)
        items = []
        for c in data:
            d = c.get("data", {})
            if d.get("score", 0) < self.min_score:
                continue
            items.append(Item(
                source=self.name,
                source_type=SourceType.news,
                external_id=d.get("id", ""),
                title=d.get("title", ""),
                url=d.get("url") or f"{BASE}{d.get('permalink', '')}",
                author=d.get("author"),
                published_at=datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc),
                fetched_at=now,
                raw_content=d.get("selftext") or d.get("title", ""),
                metrics={"score": d.get("score", 0), "comments": d.get("num_comments", 0)},
                language="en",
            ))
        return items

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        results: list[Item] = []
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": "hotspot-crawler/0.1"},
        ) as client:
            for sub in self.subreddits:
                results.extend(await self._search_sub(client, sub, topic, hours))
        return results
