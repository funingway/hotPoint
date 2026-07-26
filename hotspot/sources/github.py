import httpx
from datetime import datetime, timezone, timedelta

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API = "https://api.github.com/search/repositories"


@register_source
class GithubSource(BaseSource):
    name = "github"

    def __init__(self, min_stars: int = 50, token: str | None = None, rate_limit: float = 1.0, **_):
        self.min_stars = min_stars
        self.token = token
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d")
        params = {
            "q": f"{topic} in:name,description,readme pushed:>{since} stars:>={self.min_stars}",
            "sort": "stars", "order": "desc", "per_page": 50,
        }
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API, params=params, headers=headers)
            if resp.status_code == 403:
                return []
            resp.raise_for_status()
            data = resp.json()
        items = []
        now = datetime.now(timezone.utc)
        for r in data.get("items", []):
            if r.get("stargazers_count", 0) < self.min_stars:
                continue
            try:
                pushed = datetime.fromisoformat(r.get("pushed_at", "").replace("Z", "+00:00"))
            except ValueError:
                pushed = now
            items.append(Item(
                source=self.name,
                source_type=SourceType.github,
                external_id=str(r["id"]),
                title=r.get("full_name") or r.get("name") or "",
                url=r.get("html_url") or "",
                author=(r.get("owner") or {}).get("login"),
                published_at=pushed,
                fetched_at=now,
                raw_content=r.get("description") or "",
                metrics={"stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0)},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        owner_repo = item.title
        headers = {"Accept": "application/vnd.github.raw"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner_repo}/readme",
                    headers=headers,
                )
                readme = resp.text if resp.status_code == 200 else ""
            except httpx.HTTPError:
                readme = ""
        parts = [item.raw_content, readme[:8000]]
        return "\n\n".join(p for p in parts if p)
