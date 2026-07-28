import pytest
from datetime import datetime, timezone
from hotspot.models import Item, SourceType
from hotspot.sources.arxiv import ArxivSource


class StubClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def chat_json(self, prompt, schema_hint=None):
        self.calls += 1
        if not self.responses:
            return {"relevant": True, "relevance_score": 80, "reason": "ok"}
        return self.responses.pop(0)


def make_arxiv_item(item_id, title, abstract):
    return Item(
        source="arxiv", source_type=SourceType.paper, external_id=item_id,
        title=title, url=f"http://arxiv.org/abs/{item_id}",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content=abstract, metrics={}, language="en",
    )


@pytest.mark.asyncio
async def test_filter_by_relevance_keeps_only_relevant():
    items = [
        make_arxiv_item("1", "Relevant Paper", "About LLM"),
        make_arxiv_item("2", "Irrelevant Paper", "About cooking"),
    ]
    client = StubClient([
        {"relevant": True, "relevance_score": 80, "reason": "相关"},
        {"relevant": False, "relevance_score": 30, "reason": "不相关"},
    ])
    src = ArxivSource(max_results=50, rate_limit=10.0)
    filtered = await src.filter_by_relevance(items, topic="LLM", client=client)
    assert len(filtered) == 1
    assert filtered[0].external_id == "1"
    assert client.calls == 2
