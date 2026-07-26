import respx
import pytest
from hotspot.sources.medium import MediumSource

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Article One</title>
      <link>https://medium.com/p/abc123</link>
      <author>Alice</author>
      <pubDate>Sat, 25 Jul 2026 10:00:00 GMT</pubDate>
      <description>First article description</description>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_rss():
    respx.get("https://medium.com/feed/tag/AI").respond(text=RSS_XML)
    src = MediumSource(min_claps=0, rate_limit=10.0)
    items = await src.fetch("AI", hours=48)
    assert len(items) == 1
    item = items[0]
    assert item.source == "medium"
    assert item.source_type.value == "blog"
    assert item.title == "Article One"
    assert item.url == "https://medium.com/p/abc123"
