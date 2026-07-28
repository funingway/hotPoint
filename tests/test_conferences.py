"""conferences 数据源测试"""
import pytest
import httpx
import respx
from hotspot.sources.conferences import ConferencesSource


@pytest.fixture
def venue_response():
    """模拟 DBLP 单 venue 搜索响应"""
    return {
        "result": {
            "hits": {
                "@total": "2",
                "hit": [
                    {
                        "info": {
                            "title": "Attention Is All You Need",
                            "venue": "NeurIPS",
                            "year": "2017",
                            "key": "conf/nips/vaswani17",
                            "ee": "https://arxiv.org/abs/1706.03762",
                            "authors": {
                                "author": [
                                    {"text": "Ashish Vaswani"},
                                    {"text": "Noam Shazeer"},
                                ]
                            },
                        }
                    },
                    {
                        "info": {
                            "title": "BERT: Pre-training of Deep Transformers",
                            "venue": "NeurIPS",
                            "year": "2019",
                            "key": "conf/nips/devlin19",
                            "ee": "https://arxiv.org/abs/1810.04805",
                            "authors": {"author": {"text": "Jacob Devlin"}},
                        }
                    },
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_conferences_fetch(venue_response):
    src = ConferencesSource(conferences=["NeurIPS"], journals=False, per_venue=5)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://dblp.org/search/publ/api").respond(
            json=venue_response
        )
        items = await src.fetch("LLM", 24)

    assert len(items) == 2
    assert items[0].source == "conferences"
    assert items[0].source_type.value == "paper"
    assert "NeurIPS" in items[0].raw_content
    assert items[0].url.startswith("https://")
    assert items[0].author  # 应有作者


@pytest.mark.asyncio
async def test_conferences_dedup(venue_response):
    """同一标题命中多 venue 应去重"""
    src = ConferencesSource(
        conferences=["NeurIPS", "ICML"], journals=False, per_venue=5
    )

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://dblp.org/search/publ/api").respond(
            json=venue_response  # 两个 venue 返回相同数据
        )
        items = await src.fetch("LLM", 24)

    # 去重后应只有 2 条（而非 4 条）
    assert len(items) == 2


@pytest.mark.asyncio
async def test_conferences_error_handling():
    """DBLP API 失败时应返回空列表，不抛异常"""
    src = ConferencesSource(conferences=["NeurIPS"], journals=False)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://dblp.org/search/publ/api").respond(status_code=500)
        items = await src.fetch("LLM", 24)

    assert items == []


def test_conferences_registered():
    from hotspot.sources import SOURCE_REGISTRY
    import hotspot.sources.conferences  # noqa: F401
    assert "conferences" in SOURCE_REGISTRY
