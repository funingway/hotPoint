import respx
import pytest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from hotspot.sources.medium import MediumSource


def _build_rss_xml(pub_date_str: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Article One</title>
      <link>https://medium.com/p/abc123</link>
      <author>Alice</author>
      <pubDate>{pub_date_str}</pubDate>
      <description>First article description</description>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_rss():
    recent_dt = datetime.now(timezone.utc) - timedelta(hours=2)
    pub_date_str = format_datetime(recent_dt, usegmt=True)
    rss_xml = _build_rss_xml(pub_date_str)
    respx.get("https://medium.com/feed/tag/AI").respond(text=rss_xml)
    src = MediumSource(min_claps=0, rate_limit=10.0)
    items = await src.fetch("AI", hours=48)
    assert len(items) == 1
    item = items[0]
    assert item.source == "medium"
    assert item.source_type.value == "blog"
    assert item.title == "Article One"
    assert item.url == "https://medium.com/p/abc123"
