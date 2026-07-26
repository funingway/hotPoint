import httpx
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter


@register_source
class MediumSource(BaseSource):
    name = "medium"

    def __init__(self, min_claps: int = 100, rate_limit: float = 1.0, **_):
        self.min_claps = min_claps
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        url = f"https://medium.com/feed/tag/{topic}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
        root = ET.fromstring(text)
        items = []
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            pub_str = item.findtext("pubDate") or ""
            try:
                pub_dt = parsedate_to_datetime(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if pub_dt.timestamp() < cutoff:
                continue
            desc = (item.findtext("description") or "").strip()
            items.append(Item(
                source=self.name,
                source_type=SourceType.blog,
                external_id=link.split("/")[-1] or link,
                title=title,
                url=link,
                author=item.findtext("author") or item.findtext("dc:creator", default=None, namespaces={"dc": "http://purl.org/dc/elements/1.1/"}),
                published_at=pub_dt,
                fetched_at=now,
                raw_content=desc,
                metrics={},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        await self._limiter.acquire()
        try:
            from trafilatura import fetch_url, extract
            html = fetch_url(item.url)
            if not html:
                return item.raw_content
            text = extract(html, include_comments=False, include_tables=False) or item.raw_content
            return text[:10000]
        except Exception:
            return item.raw_content
