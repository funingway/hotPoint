import respx
import pytest
from hotspot.sources.reddit import RedditSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_items_filtered_by_score():
    respx.get("https://www.reddit.com/r/programming/search.json").respond(
        json={
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc",
                            "title": "Big AI News",
                            "url": "https://example.com/news",
                            "author": "alice",
                            "created_utc": 1784000000.0,
                            "score": 200,
                            "num_comments": 50,
                            "selftext": "Self text",
                            "permalink": "/r/programming/comments/abc/big_ai_news/",
                        }
                    },
                    {
                        "data": {
                            "id": "def",
                            "title": "Low score filtered",
                            "url": "https://example.com/low",
                            "author": "bob",
                            "created_utc": 1784000000.0,
                            "score": 5,
                            "num_comments": 1,
                            "selftext": "",
                            "permalink": "/r/programming/comments/def/low/",
                        }
                    },
                ]
            }
        }
    )
    src = RedditSource(subreddits=["programming"], min_score=20, rate_limit=10.0)
    items = await src.fetch("AI", hours=24)
    assert len(items) == 1
    item = items[0]
    assert item.source == "reddit"
    assert item.external_id == "abc"
    assert item.metrics["score"] == 200
    assert item.url == "https://example.com/news"
