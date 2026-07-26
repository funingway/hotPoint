import httpx
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


@register_source
class ArxivSource(BaseSource):
    name = "arxiv"

    def __init__(self, max_results: int = 50, rate_limit: float = 1.0, **_):
        self.max_results = max_results
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        params = {
            "search_query": f"all:{topic}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(self.max_results),
        }
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            text = resp.text
        root = ET.fromstring(text)
        items = []
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        for entry in root.findall("atom:entry", NS):
            id_url = (entry.findtext("atom:id", default="", namespaces=NS) or "").strip()
            m = re.search(r"arxiv\.org/abs/(.+)$", id_url)
            ext_id = m.group(1) if m else id_url.split("/")[-1]
            published = entry.findtext("atom:published", default="", namespaces=NS) or ""
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub_dt.timestamp() < cutoff:
                continue
            link = ""
            for l in entry.findall("atom:link", NS):
                if l.get("rel") == "alternate":
                    link = l.get("href") or ""
                    break
            if not link:
                link = id_url
            author_elem = entry.find("atom:author", NS)
            author = author_elem.findtext("atom:name", default=None, namespaces=NS) if author_elem is not None else None
            items.append(Item(
                source=self.name,
                source_type=SourceType.paper,
                external_id=ext_id,
                title=(entry.findtext("atom:title", default="", namespaces=NS) or "").strip(),
                url=link,
                author=author,
                published_at=pub_dt,
                fetched_at=now,
                raw_content=(entry.findtext("atom:summary", default="", namespaces=NS) or "").strip(),
                metrics={},
                language="en",
            ))
        return items
