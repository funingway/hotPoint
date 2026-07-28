"""AI 顶会数据源（通过 DBLP API 抓取）。

覆盖 NeurIPS / ICML / ICLR / CVPR / ICCV / ECCV / ACL / EMNLP /
AAAI / IJCAI / KDD / SIGIR / ICRA / IROS 等顶级会议论文。
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

logger = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"

# AI 相关顶会（DBLP venue 名称）——默认启用核心 8 大会议
TOP_CONFERENCES: list[str] = [
    "NeurIPS", "ICML", "ICLR",
    "CVPR", "ACL", "EMNLP",
    "AAAI", "IJCAI",
]

# 扩展会议（用户可在 config.yaml 中追加）
EXTENDED_CONFERENCES: list[str] = [
    "ICCV", "ECCV", "NAACL",
    "KDD", "SIGIR",
    "ICRA", "IROS",
]

# DBLP 顶级期刊
TOP_JOURNALS: list[str] = [
    "TPAMI", "IJCV", "JMLR", "TACL",
]


@register_source
class ConferencesSource(BaseSource):
    """AI 顶会论文数据源，通过 DBLP API 按 venue + topic 搜索。"""

    name = "conferences"

    def __init__(
        self,
        conferences: list[str] | None = None,
        journals: list[str] | None = None,
        per_venue: int = 15,
        rate_limit: float = 1.0,
        timeout: float = 12.0,
        **_,
    ):
        self.venues = conferences or TOP_CONFERENCES
        if journals is not False:
            self.venues = self.venues + (journals or [])
        self.per_venue = per_venue
        self.timeout = timeout
        self._limiter = RateLimiter(rate_limit)

    async def _search_venue(
        self, client: httpx.AsyncClient, venue: str, topic: str,
    ) -> list[Item]:
        """搜索单个 venue 的论文（含 1 次重试）。"""
        query = f"venue:{venue} {topic}" if topic else f"venue:{venue}"
        params = {"q": query, "format": "json", "h": self.per_venue}

        for attempt in range(2):  # 最多重试 1 次
            await self._limiter.acquire()
            try:
                resp = await client.get(DBLP_API, params=params)
                if resp.status_code == 429:
                    if attempt == 0:
                        logger.warning(f"DBLP rate limited on venue={venue}, retrying…")
                        await asyncio.sleep(3.0)
                        continue
                    logger.warning(f"DBLP rate limited on venue={venue}, giving up")
                    return []
                resp.raise_for_status()
            except httpx.HTTPError as e:
                if attempt == 0:
                    logger.warning(f"DBLP venue={venue} failed: {e}, retrying…")
                    await asyncio.sleep(2.0)
                    continue
                logger.warning(f"DBLP venue={venue} fetch failed: {e}")
                return []

            try:
                data = resp.json()
            except Exception:
                logger.warning(f"DBLP venue={venue} JSON parse failed")
                return []
            break
        else:
            return []

        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        now = datetime.now(timezone.utc)
        items: list[Item] = []
        for h in hits:
            info = h.get("info", {})
            title = info.get("title", "").strip()
            if not title:
                continue
            # 作者可能是 dict 或 list
            authors_data = info.get("authors", {}).get("author", [])
            if isinstance(authors_data, dict):
                authors_data = [authors_data]
            author_names = [a.get("text", "") for a in authors_data if isinstance(a, dict)]
            author_str = ", ".join(author_names[:3])
            if len(author_names) > 3:
                author_str += f" 等 {len(author_names)} 人"

            year_str = info.get("year", "")
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                year = now.year
            published = datetime(year, 1, 1, tzinfo=timezone.utc)

            # ee 是外部链接（如 arxiv），url 是 DBLP 页面
            ext_url = info.get("ee", "") or info.get("url", "")
            dblp_key = info.get("key", "")

            items.append(Item(
                source=self.name,
                source_type=SourceType.paper,
                external_id=dblp_key or f"dblp-{venue}-{title[:20]}",
                title=title,
                url=ext_url or f"https://dblp.org/rec/{dblp_key}",
                author=author_str,
                published_at=published,
                fetched_at=now,
                raw_content=f"[{venue} {year}] {title}\n作者: {author_str}",
                metrics={"year": year, "venue": venue},
                language="en",
            ))
        return items

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        """串行搜索所有顶会（避免触发 DBLP 限流）。"""
        headers = {
            "User-Agent": "hotpoint/1.0 (research crawler; +https://github.com/funingway/hotPoint)",
            "Accept": "application/json",
        }
        results: list[Item] = []
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers=headers,
        ) as client:
            for venue in self.venues:
                venue_items = await self._search_venue(client, venue, topic)
                results.extend(venue_items)

        # 按话题去重（同一论文可能命中多个 venue）
        seen: set[str] = set()
        unique: list[Item] = []
        for it in results:
            key = it.title.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(it)

        logger.info(f"conferences: {len(unique)} papers from "
                    f"{len(self.venues)} venues (raw={len(results)})")
        return unique
