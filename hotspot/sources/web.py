"""通用 Web 数据源适配器

支持用户自定义添加任意网站：
- RSS/Atom Feed（自动检测）
- 普通网页（HTML 解析提取链接）

通过 {topic} 占位符支持话题注入，例如：
  https://example.com/feed?q={topic}
  https://news.ycombinator.com/

配置示例（config.yaml）:
  custom_sources:
    - name: techcrunch
      url: "https://techcrunch.com/feed/"
      source_type: news
      enabled: true
    - name: my_blog
      url: "https://blog.example.com/tag/{topic}/rss"
      source_type: blog
      enabled: true
"""
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter


# RSS/Atom 命名空间
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _parse_date(s: str) -> datetime | None:
    """尝试多种日期格式解析"""
    if not s:
        return None
    # RFC 2822 (RSS)
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    # ISO 8601 (Atom)
    try:
        # 兼容带 Z 的 ISO
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    return None


def _strip_html(text: str) -> str:
    """去除 HTML 标签"""
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(strip=True)[:2000]


def _looks_like_feed(text: str) -> bool:
    """检测文本是否是 RSS/Atom feed"""
    head = text[:500].lower()
    return "<rss" in head or "<feed" in head or "<rdf" in head


@register_source
class WebSource(BaseSource):
    """通用 Web 数据源

    通过 source_config 字段接收运行时配置（name, url, source_type），
    使一个类可以服务多个用户自定义源。
    """
    name = "web"

    def __init__(self, rate_limit: float = 1.0,
                 source_config: dict | None = None, **_):
        self._limiter = RateLimiter(rate_limit)
        # source_config 由 Web 应用动态注入：{"name": "...", "url": "...", "source_type": "news"}
        self._source_config = source_config or {}

    @property
    def custom_name(self) -> str:
        return self._source_config.get("name", "web")

    @property
    def custom_url(self) -> str:
        return self._source_config.get("url", "")

    @property
    def custom_type(self) -> SourceType:
        st = self._source_config.get("source_type", "news")
        try:
            return SourceType(st)
        except ValueError:
            return SourceType.news

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        if not self.custom_url:
            return []

        # 话题注入
        url = self.custom_url.replace("{topic}", httpx.URL(topic).path.strip("/"))
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600

        await self._limiter.acquire()
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "hotPoint/0.1 (research crawler)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                text = resp.text
        except Exception:
            return []

        # 自动检测 feed vs 网页
        if _looks_like_feed(text):
            items = self._parse_feed(text, now, cutoff)
        else:
            items = self._parse_html(text, url, now, cutoff)

        # 标记来源
        for it in items:
            it.source = self.custom_name
            it.source_type = self.custom_type

        return items

    def _parse_feed(self, text: str, now: datetime, cutoff: float) -> list[Item]:
        """解析 RSS/Atom feed"""
        items = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        # RSS <item>
        for node in root.findall(".//item"):
            link = (node.findtext("link") or "").strip()
            title = (node.findtext("title") or "").strip()
            pub_str = node.findtext("pubDate") or ""
            desc = node.findtext("description") or ""
            author = (node.findtext("author") or
                      node.findtext("dc:creator", default="", namespaces=NS))
            guid = (node.findtext("guid") or link).strip()

            pub_dt = _parse_date(pub_str)
            if pub_dt is None:
                continue
            if pub_dt.timestamp() < cutoff:
                continue

            items.append(Item(
                source=self.custom_name,
                source_type=self.custom_type,
                external_id=guid or link,
                title=title,
                url=link,
                author=author or None,
                published_at=pub_dt,
                fetched_at=now,
                raw_content=_strip_html(desc),
                metrics={},
                language="en",
            ))

        # Atom <entry>
        for node in root.findall(".//atom:entry", NS):
            link = ""
            link_node = node.find("atom:link", NS)
            if link_node is not None:
                link = link_node.get("href", "").strip()
            title = (node.findtext("atom:title", default="", namespaces=NS) or "").strip()
            pub_str = (node.findtext("atom:published", default="",
                                     namespaces=NS) or
                       node.findtext("atom:updated", default="", namespaces=NS))
            summary = (node.findtext("atom:summary", default="",
                                     namespaces=NS) or
                       node.findtext("atom:content", default="", namespaces=NS))
            author_node = node.find("atom:author/atom:name", NS)
            author = author_node.text if author_node is not None else None
            guid = (node.findtext("atom:id", default="", namespaces=NS) or link).strip()

            pub_dt = _parse_date(pub_str)
            if pub_dt is None:
                continue
            if pub_dt.timestamp() < cutoff:
                continue

            items.append(Item(
                source=self.custom_name,
                source_type=self.custom_type,
                external_id=guid or link,
                title=title,
                url=link,
                author=author,
                published_at=pub_dt,
                fetched_at=now,
                raw_content=_strip_html(summary),
                metrics={},
                language="en",
            ))

        return items

    def _parse_html(self, text: str, base_url: str,
                    now: datetime, cutoff: float) -> list[Item]:
        """解析普通 HTML 页面，提取文章链接"""
        items = []
        soup = BeautifulSoup(text, "html.parser")

        # 常见文章选择器
        selectors = [
            "article", "main article", ".post", ".article",
            ".entry", ".story", ".card",
        ]

        seen_urls = set()
        for sel in selectors:
            for art in soup.select(sel):
                a = art.find("a", href=True)
                if not a:
                    continue
                href = a["href"].strip()
                if not href or href.startswith("#"):
                    continue
                # 相对 URL 转绝对
                full_url = httpx.URL(base_url).join(href)
                if str(full_url) in seen_urls:
                    continue
                seen_urls.add(str(full_url))

                title = (art.find(["h1", "h2", "h3"]) or a).get_text(strip=True)
                if not title:
                    title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # 提取时间
                time_tag = art.find("time")
                pub_dt = None
                if time_tag:
                    pub_dt = _parse_date(time_tag.get("datetime") or time_tag.get_text())

                # 摘要
                desc = art.get_text(" ", strip=True)[:500]

                items.append(Item(
                    source=self.custom_name,
                    source_type=self.custom_type,
                    external_id=str(full_url),
                    title=title[:200],
                    url=str(full_url),
                    published_at=pub_dt or now,
                    fetched_at=now,
                    raw_content=desc,
                    metrics={},
                    language="en",
                ))

        # 退而求其次：所有 <a> 标签
        if not items:
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("#") or href.startswith("javascript:"):
                    continue
                full_url = httpx.URL(base_url).join(href)
                if str(full_url) in seen_urls:
                    continue
                seen_urls.add(str(full_url))
                title = a.get_text(strip=True)
                if not title or len(title) < 8:
                    continue
                items.append(Item(
                    source=self.custom_name,
                    source_type=self.custom_type,
                    external_id=str(full_url),
                    title=title[:200],
                    url=str(full_url),
                    published_at=now,
                    fetched_at=now,
                    raw_content=title,
                    metrics={},
                    language="en",
                ))

        # HTML 解析无法可靠获取发布时间，所以不按 cutoff 过滤
        return items[:50]

    async def fetch_full(self, item: Item) -> str:
        await self._limiter.acquire()
        try:
            from trafilatura import fetch_url, extract
            html = fetch_url(item.url)
            if not html:
                return item.raw_content
            text = extract(html, include_comments=False,
                          include_tables=False) or item.raw_content
            return text[:10000]
        except Exception:
            return item.raw_content
