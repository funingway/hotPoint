import respx
import pytest
from hotspot.sources.devto import DevtoSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_articles():
    respx.get("https://dev.to/api/articles").respond(
        json=[
            {
                "id": 1, "title": "Article One",
                "url": "https://dev.to/alice/article-one",
                "published_at": "2026-07-25T10:00:00Z",
                "positive_reactions_count": 100,
                "comments_count": 10,
                "description": "First article",
                "user": {"username": "alice"},
                "tag_list": "ai",
            }
        ]
    )
    src = DevtoSource(min_reactions=50, rate_limit=10.0)
    items = await src.fetch("ai", hours=48)
    assert len(items) == 1
    item = items[0]
    assert item.source == "devto"
    assert item.external_id == "1"
    assert item.metrics["reactions"] == 100
