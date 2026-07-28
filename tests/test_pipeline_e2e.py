import pytest
from datetime import datetime, timezone

from hotspot.models import Item, SourceType, SourceRunStatus, ReportMeta
from hotspot.pipeline.analyze import (
    run_comparisons, run_cluster, run_suggestions, pick_top_k_items,
)
from hotspot.pipeline.render import render_report, ReportContext


class StubOllamaClient:
    async def chat_json(self, prompt, schema_hint=None):
        if "winner" in prompt:
            return {"winner": "A", "reason": "A 更新鲜", "a_score": 90, "b_score": 60}
        if "themes" in prompt:
            return {"themes": [{"name": "AI突破", "description": "desc",
                                "item_ids": ["a", "b"], "heat_score": 85}]}
        if "suggestions" in prompt:
            return {"suggestions": [{
                "title": "AI 新突破", "angle": "技术", "hook": "你敢信",
                "key_points": ["p1"], "target_audience": "极客",
                "visual_hint": "动画", "evidence_ids": ["a"],
                "freshness_tag": "fresh", "estimated_value": 88,
            }]}
        return {}

    async def ping(self):
        return True


def make_item(item_id, title="T", content="content"):
    it = Item(
        source="hn", source_type=SourceType.news, external_id=item_id,
        title=title, url=f"https://x.com/{item_id}",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="summary", full_content=content,
        metrics={"points": 10},
    )
    it.id = item_id
    return it


@pytest.mark.asyncio
async def test_full_pipeline_produces_report():
    items = [make_item("a", "A News"), make_item("b", "B News")]
    client = StubOllamaClient()

    _, comps = await run_comparisons(
        items, topic="AI", client=client,
        max_comparisons=3, k=32, band=200, early_stop_threshold=50,
    )
    assert len(comps) == 3

    top = pick_top_k_items(items, k=2)
    assert len(top) == 2

    themes = await run_cluster(top, topic="AI", client=client)
    assert len(themes) == 1

    sugs_by_theme = {}
    for t in themes:
        ti = [i for i in top if i.id in t.item_ids][:3]
        sugs_by_theme[t.name] = await run_suggestions(
            topic="AI", theme_name=t.name,
            theme_description=t.description, items=ti, client=client,
        )
    assert len(sugs_by_theme["AI突破"]) == 1

    ctx = ReportContext(
        meta=ReportMeta(
            run_id="r1", topic="AI", hours=24,
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            item_count=2, comparison_count=len(comps), elapsed_sec=5.0,
            file_path="x.md",
        ),
        source_statuses=[SourceRunStatus(source="hn", status="success", fetched_count=2)],
        themes=themes,
        suggestions_by_theme=sugs_by_theme,
        top_items=top, all_items=items,
        comparison_observations=comps[:10],
        config_snapshot={"model": "stub"},
    )
    md = render_report(ctx)
    assert "AI 自媒体选题调研报告" in md
    assert "AI 新突破" in md
    assert "AI突破" in md
