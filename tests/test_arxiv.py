import respx
import pytest
from hotspot.sources.arxiv import ArxivSource

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Paper One</title>
    <author><name>Alice</name></author>
    <published>2026-07-25T10:00:00Z</published>
    <summary>This is the abstract.</summary>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.67890v1</id>
    <title>Paper Two</title>
    <author><name>Bob</name></author>
    <published>2026-07-25T11:00:00Z</published>
    <summary>Second abstract.</summary>
    <link href="http://arxiv.org/abs/2401.67890v1" rel="alternate"/>
  </entry>
</feed>"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_atom_feed():
    respx.get("http://export.arxiv.org/api/query").respond(text=ATOM_XML)
    src = ArxivSource(max_results=50, rate_limit=10.0)
    items = await src.fetch("world models", hours=48)
    assert len(items) == 2
    item = items[0]
    assert item.source == "arxiv"
    assert item.source_type.value == "paper"
    assert item.external_id == "2401.12345v1"
    assert item.title == "Paper One"
    assert item.url == "http://arxiv.org/abs/2401.12345v1"
    assert "abstract" in item.raw_content.lower()
