import respx
import pytest
from datetime import datetime, timezone
from hotspot.sources.hackernews import HackerNewsSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_items_filtered_by_points():
    now = int(datetime(2026, 7, 26, 12, tzinfo=timezone.utc).timestamp())
    respx.get("https://hn.algolia.com/api/v1/search").respond(
        json={
            "hits": [
                {
                    "objectID": "12345",
                    "title": "New AI Breakthrough",
                    "url": "https://example.com/article",
                    "author": "alice",
                    "created_at_i": now - 3600,
                    "points": 150,
                    "num_comments": 30,
                    "story_text": "",
                },
                {
                    "objectID": "12346",
                    "title": "Low points filtered out",
                    "url": "https://example.com/low",
                    "author": "bob",
                    "created_at_i": now - 7200,
                    "points": 5,
                    "num_comments": 1,
                    "story_text": "",
                },
            ]
        }
    )
    src = HackerNewsSource(min_points=10, rate_limit=10.0)
    items = await src.fetch("AI", hours=24)
    assert len(items) == 1
    item = items[0]
    assert item.source == "hackernews"
    assert item.external_id == "12345"
    assert item.title == "New AI Breakthrough"
    assert item.metrics["points"] == 150
    assert item.url == "https://example.com/article"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_story_text_when_no_url():
    respx.get("https://hn.algolia.com/api/v1/search").respond(
        json={
            "hits": [
                {
                    "objectID": "99",
                    "title": "Ask HN",
                    "url": "",
                    "author": "x",
                    "created_at_i": 1784000000,
                    "points": 50,
                    "num_comments": 10,
                    "story_text": "Self post content",
                }
            ]
        }
    )
    src = HackerNewsSource(min_points=10, rate_limit=10.0)
    items = await src.fetch("test", hours=24)
    assert items[0].url == "https://news.ycombinator.com/item?id=99"
    assert items[0].raw_content == "Self post content"
