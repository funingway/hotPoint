from datetime import datetime, timezone
from hotspot.models import Item, SourceType, ReportMeta, Theme, Suggestion


def test_item_creation_with_defaults():
    item = Item(
        source="hackernews",
        source_type=SourceType.news,
        external_id="123",
        title="Test",
        url="https://example.com",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
        raw_content="summary",
        metrics={"points": 10},
    )
    assert item.elo == 1000
    assert item.language == "en"
    assert item.fulltext_failed is False
    assert item.full_content is None
    assert item.summary is None
    assert item.id


def test_item_source_type_enum():
    assert SourceType.news.value == "news"
    assert SourceType.paper.value == "paper"
    assert SourceType.blog.value == "blog"
    assert SourceType.github.value == "github"


def test_theme_creation():
    t = Theme(name="AGI", description="desc", item_ids=["a", "b"], heat_score=80)
    assert t.name == "AGI"
    assert t.heat_score == 80


def test_suggestion_creation():
    s = Suggestion(
        title="标题", angle="角度", hook="钩子",
        key_points=["p1"], target_audience="受众",
        visual_hint="提示", evidence_ids=["id1"],
        freshness_tag="counter_intuitive", estimated_value=85,
    )
    assert s.freshness_tag == "counter_intuitive"
    assert s.estimated_value == 85


def test_report_meta_creation():
    m = ReportMeta(
        run_id="abc", topic="AGI", hours=24,
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        item_count=10, comparison_count=30, elapsed_sec=120.5,
        file_path="reports/x.md", degraded=False,
    )
    assert m.topic == "AGI"
    assert m.degraded is False
