from datetime import datetime, timezone
from hotspot.pipeline.render import render_report, ReportContext
from hotspot.models import Item, SourceType, Theme, Suggestion, ReportMeta, SourceRunStatus


def make_item(item_id="1", title="T", elo=1000):
    it = Item(
        source="hn", source_type=SourceType.news, external_id=item_id,
        title=title, url=f"https://x.com/{item_id}",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="summary", metrics={"points": 10},
    )
    it.id = item_id
    it.elo = elo
    return it


def test_render_report_contains_all_sections():
    ctx = ReportContext(
        meta=ReportMeta(
            run_id="r1", topic="AI", hours=24,
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            item_count=2, comparison_count=6, elapsed_sec=10.0,
            file_path="x.md",
        ),
        source_statuses=[
            SourceRunStatus(source="hn", status="success", fetched_count=2),
        ],
        themes=[Theme(name="AGI", description="desc", item_ids=["1", "2"], heat_score=80)],
        suggestions_by_theme={
            "AGI": [Suggestion(
                title="标题", angle="角度", hook="钩子",
                key_points=["p1"], target_audience="受众",
                visual_hint="视觉", evidence_ids=["1"],
                freshness_tag="fresh", estimated_value=85,
            )]
        },
        top_items=[make_item("1", "Top1", 1200), make_item("2", "Top2", 1100)],
        all_items=[make_item("1", "Top1", 1200), make_item("2", "Top2", 1100)],
        comparison_observations=[{"reason": "A 更新", "winner": "1"}],
        config_snapshot={"llm": {"model": "gemma4-12b"}},
    )
    md = render_report(ctx)
    assert "AI 自媒体选题调研报告" in md
    assert "执行摘要" in md
    assert "主题概览" in md
    assert "选题建议" in md
    assert "Top 20 内容排行" in md
    assert "对比观察" in md
    assert "完整候选列表" in md
    assert "运行参数" in md
    assert "标题" in md
    assert "gemma4-12b" in md
