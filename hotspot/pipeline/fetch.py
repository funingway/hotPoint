import asyncio
import logging

from hotspot.models import Item, SourceRunStatus

logger = logging.getLogger(__name__)


async def run_fetch(sources: list, topic: str, hours: int) -> tuple[list[Item], list[SourceRunStatus]]:
    async def _one(src):
        try:
            items = await src.fetch(topic, hours)
            return items, SourceRunStatus(
                source=src.name, status="success",
                fetched_count=len(items), error=None,
            )
        except Exception as e:
            logger.warning(f"Source {src.name} failed: {e}")
            return [], SourceRunStatus(
                source=src.name, status="failed",
                fetched_count=0, error=str(e),
            )

    results = await asyncio.gather(*[_one(s) for s in sources])
    all_items: list[Item] = []
    all_statuses: list[SourceRunStatus] = []
    for items, status in results:
        all_items.extend(items)
        all_statuses.append(status)
    return all_items, all_statuses


async def run_fulltext(items: list[Item], source_map: dict) -> None:
    async def _one(item: Item):
        src = source_map.get(item.source)
        if src is None:
            item.full_content = item.raw_content
            return
        try:
            text = await src.fetch_full(item)
            item.full_content = text
            item.fulltext_failed = False
        except Exception as e:
            logger.warning(f"Fulltext fetch failed for {item.url}: {e}")
            item.full_content = item.raw_content
            item.fulltext_failed = True

    await asyncio.gather(*[_one(i) for i in items])
