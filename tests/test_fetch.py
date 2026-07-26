import pytest
from datetime import datetime, timezone
from hotspot.pipeline.fetch import run_fetch, run_fulltext
from hotspot.models import Item, SourceType


class FakeSource:
    name = "fake"

    async def fetch(self, topic, hours):
        return [Item(
            source="fake", source_type=SourceType.news, external_id="1",
            title=f"{topic} item", url="https://x.com",
            published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            raw_content="summary", metrics={"points": 10},
        )]

    async def fetch_full(self, item):
        return "FULL TEXT"


class FailingSource:
    name = "fail"

    async def fetch(self, topic, hours):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_run_fetch_invokes_all_sources():
    items, statuses = await run_fetch([FakeSource()], topic="AI", hours=24)
    assert len(items) == 1
    assert items[0].title == "AI item"
    assert len(statuses) == 1
    assert statuses[0].source == "fake"
    assert statuses[0].status == "success"


@pytest.mark.asyncio
async def test_run_fulltext_replaces_full_content():
    item = Item(
        source="fake", source_type=SourceType.news, external_id="1",
        title="x", url="https://x.com",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="summary", metrics={},
    )
    await run_fulltext([item], source_map={"fake": FakeSource()})
    assert item.full_content == "FULL TEXT"


@pytest.mark.asyncio
async def test_run_fetch_records_failure_without_blocking():
    items, statuses = await run_fetch([FakeSource(), FailingSource()], topic="AI", hours=24)
    assert len(items) == 1
    fail_status = [s for s in statuses if s.source == "fail"]
    assert len(fail_status) == 1
    assert fail_status[0].status == "failed"
    assert "boom" in (fail_status[0].error or "")
