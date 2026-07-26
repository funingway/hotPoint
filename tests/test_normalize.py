from datetime import datetime, timezone
from hotspot.models import Item, SourceType
from hotspot.pipeline.normalize import dedupe_items, normalize_title


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("Hello, World!") == "hello world"
    assert normalize_title("AI: The Future?") == "ai the future"


def make_item(source, ext_id, title, url="https://x.com", metrics=None):
    return Item(
        source=source, source_type=SourceType.news, external_id=ext_id,
        title=title, url=url,
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
        raw_content="", metrics=metrics or {},
    )


def test_dedupe_same_source_same_ext_id_merges():
    a = make_item("hn", "1", "A", metrics={"points": 100})
    a2 = make_item("hn", "1", "A duplicate", metrics={"points": 100})
    result = dedupe_items([a, a2])
    assert len(result) == 1


def test_dedupe_cross_source_same_title_merges():
    a = make_item("hn", "1", "Same Title", url="https://a.com", metrics={"points": 50})
    b = make_item("reddit", "x", "Same Title", url="https://b.com", metrics={"score": 200})
    result = dedupe_items([a, b])
    assert len(result) == 1


def test_dedupe_different_titles_kept():
    a = make_item("hn", "1", "Title A")
    b = make_item("hn", "2", "Title B")
    result = dedupe_items([a, b])
    assert len(result) == 2
