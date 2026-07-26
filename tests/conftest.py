import pytest


@pytest.fixture
def sample_item_dict():
    return {
        "source": "hackernews",
        "source_type": "news",
        "external_id": "12345",
        "title": "Test Title",
        "url": "https://example.com/123",
        "author": "alice",
        "published_at": "2026-07-26T10:00:00+00:00",
        "fetched_at": "2026-07-26T12:00:00+00:00",
        "raw_content": "Test summary content",
        "metrics": {"points": 100, "comments": 20},
        "language": "en",
    }
