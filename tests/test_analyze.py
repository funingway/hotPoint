import pytest
from datetime import datetime, timezone
from hotspot.pipeline.analyze import (
    run_comparisons, run_cluster, run_suggestions, pick_top_k_items,
)
from hotspot.models import Item, SourceType


class MockOllamaClient:
    def __init__(self, responses):
        self.responses = list(responses)

    async def chat_json(self, prompt, schema_hint=None):
        if not self.responses:
            return {"winner": "A", "reason": "default", "a_score": 50, "b_score": 50}
        return self.responses.pop(0)


def make_item(item_id, title="T", elo=1000, content="content"):
    it = Item(
        source="hn", source_type=SourceType.news, external_id=item_id,
        title=title, url=f"https://x.com/{item_id}",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="summary", full_content=content,
        metrics={"points": 10},
    )
    it.id = item_id
    it.elo = elo
    return it


@pytest.mark.asyncio
async def test_run_comparisons_updates_elo(monkeypatch):
    # 让 random.choice 总是返回第一个元素，使 pick_opponents 顺序确定
    import hotspot.pipeline.elo as elo_mod
    monkeypatch.setattr(elo_mod.random, "choice", lambda seq: seq[0])

    items = [make_item("a"), make_item("b")]
    client = MockOllamaClient([
        {"winner": "A", "reason": "A fresh", "a_score": 90, "b_score": 50},
    ])
    ranker, comparisons = await run_comparisons(
        items, topic="AI", client=client,
        max_comparisons=1, k=32, band=200, early_stop_threshold=50,
    )
    assert len(comparisons) == 1
    assert comparisons[0]["winner"] == "a"
    assert ranker.get_elo("a") > 1000
    assert ranker.get_elo("b") < 1000


@pytest.mark.asyncio
async def test_run_cluster_returns_themes():
    items = [make_item("a", "AI News"), make_item("b", "AI News 2")]
    client = MockOllamaClient([
        {"themes": [{"name": "AI", "description": "desc", "item_ids": ["a", "b"], "heat_score": 80}]}
    ])
    themes = await run_cluster(items, topic="AI", client=client)
    assert len(themes) == 1
    assert themes[0].name == "AI"
    assert themes[0].heat_score == 80


@pytest.mark.asyncio
async def test_run_suggestions_returns_list():
    items = [make_item("a", "AI News")]
    client = MockOllamaClient([
        {"suggestions": [{
            "title": "AI 新突破", "angle": "技术", "hook": "你敢信？",
            "key_points": ["p1"], "target_audience": "极客",
            "visual_hint": "动画", "evidence_ids": ["a"],
            "freshness_tag": "fresh", "estimated_value": 85,
        }]}
    ])
    suggestions = await run_suggestions(
        topic="AI", theme_name="AI", theme_description="d",
        items=items, client=client,
    )
    assert len(suggestions) == 1
    assert suggestions[0].title == "AI 新突破"


def test_pick_top_k_items_returns_sorted_by_elo():
    items = [make_item("a", elo=900), make_item("b", elo=1200), make_item("c", elo=1100)]
    top = pick_top_k_items(items, k=2)
    assert [i.id for i in top] == ["b", "c"]
