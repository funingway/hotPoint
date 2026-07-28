# hotPoint 热点抓取软件 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个本地 CLI + Web 工具，按话题抓取 6 类英文源最近 N 小时热点内容，全文抓取后用 Ollama 本地 LLM 做养蛊式 Elo 对比排序，生成中文自媒体选题调研报告。

**Architecture:** 模块化流水线（fetch → normalize → analyze → render → store），每个数据源是独立适配器实现统一 `BaseSource` 接口；LLM 调用封装为 `OllamaClient`；报告以 Markdown 文件为真相源，SQLite 仅作 Web 浏览索引；CLI 用 Typer，Web 用 FastAPI 托管极简静态页。

**Tech Stack:** Python 3.11+、Typer、Rich、httpx、Pydantic v2、pydantic-settings、PyYAML、Jinja2、markdown、trafilatura、BeautifulSoup4、FastAPI、uvicorn、Ollama（模型 `batiai/gemma4-12b:q4`）；测试用 pytest + pytest-asyncio + respx。

**Spec:** `docs/superpowers/specs/2026-07-26-hotspot-crawler-design.md`

---

## 文件结构总览

```
hotPoint/
├── pyproject.toml                 # 项目元数据 + 依赖
├── config.yaml                    # 默认配置
├── .env.example                   # GITHUB_TOKEN 模板
├── .gitignore
├── hotspot/
│   ├── __init__.py
│   ├── __main__.py                # python -m hotspot 入口
│   ├── cli.py                     # Typer CLI
│   ├── config.py                  # pydantic-settings 配置加载
│   ├── models.py                  # Item / Report / Theme 等数据模型
│   ├── sources/
│   │   ├── __init__.py            # SOURCE_REGISTRY
│   │   ├── base.py                # BaseSource + RateLimiter
│   │   ├── hackernews.py
│   │   ├── reddit.py
│   │   ├── arxiv.py
│   │   ├── github.py
│   │   ├── medium.py
│   │   └── devto.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── fetch.py               # 并发抓取 + 全文抓取调度
│   │   ├── normalize.py           # 标准化 + 去重
│   │   ├── analyze.py             # Elo 对比 + 聚类 + 选题建议
│   │   ├── elo.py                 # Elo Rating 纯算法（独立可测）
│   │   ├── render.py              # Jinja2 渲染
│   │   └── templates/
│   │       └── report.md.j2
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── ollama_client.py
│   │   └── prompts.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── sqlite_index.py
│   │   └── report_files.py
│   └── web/
│       ├── __init__.py
│       ├── app.py
│       └── static/
│           ├── list.html
│           └── style.css
├── reports/                       # 生成的报告（gitignore）
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_elo.py
    ├── test_normalize.py
    ├── test_models.py
    ├── test_config.py
    ├── test_hackernews.py
    ├── test_reddit.py
    ├── test_arxiv.py
    ├── test_github.py
    ├── test_medium.py
    ├── test_devto.py
    ├── test_ollama_client.py
    ├── test_prompts.py
    ├── test_analyze.py
    ├── test_render.py
    ├── test_sqlite_index.py
    ├── test_fetch.py
    ├── test_base_source.py
    ├── test_cli.py
    ├── test_web.py
    └── test_pipeline_e2e.py
```

---

## Task 1: 项目脚手架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `hotspot/__init__.py`
- Create: `hotspot/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "hotspot"
version = "0.1.0"
description = "Local hot-topic crawler for tech content creators"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "httpx>=0.27",
    "pydantic>=2",
    "pydantic-settings>=2",
    "pyyaml>=6",
    "jinja2>=3",
    "markdown>=3",
    "trafilatura>=1.12",
    "beautifulsoup4>=4.12",
    "python-dateutil>=2.9",
    "fastapi>=0.110",
    "uvicorn>=0.30",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "httpx>=0.27",
]

[project.scripts]
hotspot = "hotspot.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["hotspot*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 创建 .gitignore**

```
__pycache__/
*.pyc
.venv/
.env
hotspot.db
reports/
.pytest_cache/
*.egg-info/
build/
dist/
```

- [ ] **Step 3: 创建 .env.example**

```
# GitHub Personal Access Token (可选，提高 rate limit 从 60/h 到 5000/h)
GITHUB_TOKEN=
```

- [ ] **Step 4: 创建包入口**

`hotspot/__init__.py`:
```python
__version__ = "0.1.0"
```

`hotspot/__main__.py`:
```python
from hotspot.cli import app

if __name__ == "__main__":
    app()
```

`tests/__init__.py`: 空文件

- [ ] **Step 5: 创建 tests/conftest.py**

```python
import pytest


@pytest.fixture
def sample_item_dict():
    return {
        "source": "hackernews",
        "source_type": "news",
        "external_id": "12345",
        "title": "Test Title",
        "url": "https://example.com/123",
        "author": "alice",
        "published_at": "2026-07-26T10:00:00+00:00",
        "fetched_at": "2026-07-26T12:00:00+00:00",
        "raw_content": "Test summary content",
        "metrics": {"points": 100, "comments": 20},
        "language": "en",
    }
```

- [ ] **Step 6: 安装依赖并验证**

Run: `python -m pip install -e ".[dev]"`
Expected: 安装成功，无错误

- [ ] **Step 7: 初始化 git 并提交**

```bash
git init
git add pyproject.toml .gitignore .env.example hotspot/ tests/
git commit -m "chore: project scaffolding with dependencies"
```

---

## Task 2: 数据模型（models.py）

**Files:**
- Create: `hotspot/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

`tests/test_models.py`:
```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: 实现 models.py**

`hotspot/models.py`:
```python
from datetime import datetime
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    news = "news"
    paper = "paper"
    blog = "blog"
    github = "github"


class Item(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    source_type: SourceType
    external_id: str
    title: str
    url: str
    author: str | None = None
    published_at: datetime
    fetched_at: datetime
    raw_content: str
    full_content: str | None = None
    metrics: dict = Field(default_factory=dict)
    language: str = "en"
    elo: int = 1000
    fulltext_failed: bool = False
    summary: str | None = None


class Theme(BaseModel):
    name: str
    description: str
    item_ids: list[str]
    heat_score: int


class Suggestion(BaseModel):
    title: str
    angle: str
    hook: str
    key_points: list[str]
    target_audience: str
    visual_hint: str
    evidence_ids: list[str]
    freshness_tag: str
    estimated_value: int


class ReportMeta(BaseModel):
    run_id: str
    topic: str
    hours: int
    created_at: datetime
    item_count: int
    comparison_count: int
    elapsed_sec: float
    file_path: str
    degraded: bool = False
    config_snapshot: dict | None = None


class SourceRunStatus(BaseModel):
    source: str
    status: str
    fetched_count: int
    error: str | None = None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/models.py tests/test_models.py
git commit -m "feat: add core data models (Item, Theme, Suggestion, ReportMeta)"
```

---

## Task 3: 配置加载（config.py + config.yaml）

**Files:**
- Create: `hotspot/config.py`
- Create: `config.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`:
```python
from pathlib import Path
from hotspot.config import load_config


def test_load_default_config(tmp_path):
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text("""
defaults:
  hours: 24
  top_k: 20
  max_comparisons_factor: 3
  concurrency: 4
llm:
  base_url: "http://localhost:11434"
  model: "batiai/gemma4-12b:q4"
  model_path: "D:\\\\openClaw\\\\model"
  temperature: 0.3
  max_tokens: 4096
  timeout: 120
sources:
  hackernews:
    enabled: true
    min_points: 10
    rate_limit: 1.0
scoring:
  freshness: 0.30
  knowledge_gain: 0.30
  counter_intuitive: 0.20
  relevance: 0.10
  virality: 0.10
elo:
  initial: 1000
  k_factor: 32
  early_stop_threshold: 50
  band: 200
report:
  dir: "./reports"
  db_path: "./hotspot.db"
""", encoding="utf-8")
    cfg = load_config(config_yaml)
    assert cfg.defaults.hours == 24
    assert cfg.llm.model == "batiai/gemma4-12b:q4"
    assert cfg.llm.model_path == "D:\\openClaw\\model"
    assert cfg.sources["hackernews"].enabled is True
    assert cfg.scoring.freshness == 0.30
    assert cfg.elo.k_factor == 32
    assert cfg.report.dir == "./reports"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: 实现 config.py**

`hotspot/config.py`:
```python
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class DefaultsConfig(BaseModel):
    hours: int = 24
    top_k: int = 20
    max_comparisons_factor: int = 3
    concurrency: int = 4


class LlmConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "batiai/gemma4-12b:q4"
    model_path: str = "D:\\openClaw\\model"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120


class SourceConfig(BaseModel):
    enabled: bool = True
    min_points: int = 10
    rate_limit: float = 1.0
    subreddits: list[str] = []
    min_score: int = 20
    max_results: int = 50
    min_stars: int = 50
    token_env: str = "GITHUB_TOKEN"
    min_claps: int = 100
    min_reactions: int = 50


class ScoringConfig(BaseModel):
    freshness: float = 0.30
    knowledge_gain: float = 0.30
    counter_intuitive: float = 0.20
    relevance: float = 0.10
    virality: float = 0.10


class EloConfig(BaseModel):
    initial: int = 1000
    k_factor: int = 32
    early_stop_threshold: int = 50
    band: int = 200


class ReportConfig(BaseModel):
    dir: str = "./reports"
    db_path: str = "./hotspot.db"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOTSPOT_",
        env_nested_delimiter="__",
        extra="ignore",
    )
    defaults: DefaultsConfig = DefaultsConfig()
    llm: LlmConfig = LlmConfig()
    sources: dict[str, SourceConfig] = {}
    scoring: ScoringConfig = ScoringConfig()
    elo: EloConfig = EloConfig()
    report: ReportConfig = ReportConfig()


def load_config(path: Path | str | None = None) -> AppConfig:
    if path is None:
        default_path = Path("config.yaml")
        if default_path.exists():
            path = default_path
        else:
            return AppConfig()
    p = Path(path)
    if not p.exists():
        return AppConfig()
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig(**data)
```

- [ ] **Step 4: 创建默认 config.yaml**

```yaml
defaults:
  hours: 24
  top_k: 20
  max_comparisons_factor: 3
  concurrency: 4

llm:
  base_url: "http://localhost:11434"
  model: "batiai/gemma4-12b:q4"
  model_path: "D:\\openClaw\\model"
  temperature: 0.3
  max_tokens: 4096
  timeout: 120

sources:
  hackernews:
    enabled: true
    min_points: 10
    rate_limit: 1.0
  reddit:
    enabled: true
    subreddits: ["programming", "MachineLearning", "technology", "artificial"]
    min_score: 20
    rate_limit: 1.0
  arxiv:
    enabled: true
    max_results: 50
  github:
    enabled: true
    min_stars: 50
    token_env: "GITHUB_TOKEN"
  medium:
    enabled: true
    min_claps: 100
    rate_limit: 1.0
  devto:
    enabled: true
    min_reactions: 50
    rate_limit: 1.0

scoring:
  freshness: 0.30
  knowledge_gain: 0.30
  counter_intuitive: 0.20
  relevance: 0.10
  virality: 0.10

elo:
  initial: 1000
  k_factor: 32
  early_stop_threshold: 50
  band: 200

report:
  dir: "./reports"
  db_path: "./hotspot.db"
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add hotspot/config.py config.yaml tests/test_config.py
git commit -m "feat: add YAML + env config loading with pydantic-settings"
```

---

## Task 4: BaseSource 接口与 RateLimiter

**Files:**
- Create: `hotspot/sources/__init__.py`
- Create: `hotspot/sources/base.py`
- Create: `tests/test_base_source.py`

- [ ] **Step 1: 写失败测试**

`tests/test_base_source.py`:
```python
import time
import pytest
from hotspot.sources.base import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_enforces_interval():
    rl = RateLimiter(rate=2.0)
    start = time.monotonic()
    await rl.acquire()
    await rl.acquire()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.9


@pytest.mark.asyncio
async def test_rate_limiter_first_call_immediate():
    rl = RateLimiter(rate=1.0)
    start = time.monotonic()
    await rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_base_source.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 base.py**

`hotspot/sources/base.py`:
```python
import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from hotspot.models import Item


class RateLimiter:
    def __init__(self, rate: float = 1.0):
        self._interval = 1.0 / rate if rate > 0 else 0
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last is not None:
                wait = self._interval - (now - self._last)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
            self._last = now


class BaseSource(ABC):
    name: str

    @abstractmethod
    async def fetch(self, topic: str, hours: int) -> list[Item]:
        ...

    async def fetch_full(self, item: Item) -> str:
        return item.raw_content

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)
```

`hotspot/sources/__init__.py`:
```python
from hotspot.sources.base import BaseSource, RateLimiter

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {}


def register_source(cls):
    SOURCE_REGISTRY[cls.name] = cls
    return cls
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_base_source.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/ tests/test_base_source.py
git commit -m "feat: add BaseSource interface and RateLimiter"
```

---

## Task 5: Hacker News 适配器

**Files:**
- Create: `hotspot/sources/hackernews.py`
- Create: `tests/test_hackernews.py`

- [ ] **Step 1: 写失败测试**

`tests/test_hackernews.py`:
```python
import respx
import pytest
from datetime import datetime, timezone
from hotspot.sources.hackernews import HackerNewsSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_items_filtered_by_points():
    now = int(datetime(2026, 7, 26, 12, tzinfo=timezone.utc).timestamp())
    respx.get("https://hn.algolia.com/api/v1/search").respond(
        json={
            "hits": [
                {
                    "objectID": "12345",
                    "title": "New AI Breakthrough",
                    "url": "https://example.com/article",
                    "author": "alice",
                    "created_at_i": now - 3600,
                    "points": 150,
                    "num_comments": 30,
                    "story_text": "",
                },
                {
                    "objectID": "12346",
                    "title": "Low points filtered out",
                    "url": "https://example.com/low",
                    "author": "bob",
                    "created_at_i": now - 7200,
                    "points": 5,
                    "num_comments": 1,
                    "story_text": "",
                },
            ]
        }
    )
    src = HackerNewsSource(min_points=10, rate_limit=10.0)
    items = await src.fetch("AI", hours=24)
    assert len(items) == 1
    item = items[0]
    assert item.source == "hackernews"
    assert item.external_id == "12345"
    assert item.title == "New AI Breakthrough"
    assert item.metrics["points"] == 150
    assert item.url == "https://example.com/article"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_story_text_when_no_url():
    respx.get("https://hn.algolia.com/api/v1/search").respond(
        json={
            "hits": [
                {
                    "objectID": "99",
                    "title": "Ask HN",
                    "url": "",
                    "author": "x",
                    "created_at_i": 1784000000,
                    "points": 50,
                    "num_comments": 10,
                    "story_text": "Self post content",
                }
            ]
        }
    )
    src = HackerNewsSource(min_points=10, rate_limit=10.0)
    items = await src.fetch("test", hours=24)
    assert items[0].url == "https://news.ycombinator.com/item?id=99"
    assert items[0].raw_content == "Self post content"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_hackernews.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 hackernews.py**

`hotspot/sources/hackernews.py`:
```python
import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API_URL = "https://hn.algolia.com/api/v1/search"


@register_source
class HackerNewsSource(BaseSource):
    name = "hackernews"

    def __init__(self, min_points: int = 10, rate_limit: float = 1.0, **_):
        self.min_points = min_points
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        now = int(datetime.now(timezone.utc).timestamp())
        min_ts = now - hours * 3600
        params = {
            "query": topic,
            "tags": "story",
            "numericFilters": f"created_at_i>{min_ts},points>={self.min_points}",
            "hitsPerPage": 50,
        }
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        items = []
        now_dt = datetime.now(timezone.utc)
        for hit in data.get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            items.append(Item(
                source=self.name,
                source_type=SourceType.news,
                external_id=str(hit["objectID"]),
                title=hit.get("title") or "(no title)",
                url=url,
                author=hit.get("author"),
                published_at=datetime.fromtimestamp(
                    hit.get("created_at_i", now), tz=timezone.utc
                ),
                fetched_at=now_dt,
                raw_content=hit.get("story_text") or hit.get("title") or "",
                metrics={
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                },
                language="en",
            ))
        return items
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_hackernews.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/hackernews.py tests/test_hackernews.py
git commit -m "feat: add Hacker News source via Algolia Search API"
```

---

## Task 6: Reddit 适配器

**Files:**
- Create: `hotspot/sources/reddit.py`
- Create: `tests/test_reddit.py`

- [ ] **Step 1: 写失败测试**

`tests/test_reddit.py`:
```python
import respx
import pytest
from hotspot.sources.reddit import RedditSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_items_filtered_by_score():
    respx.get("https://www.reddit.com/r/programming/search.json").respond(
        json={
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc",
                            "title": "Big AI News",
                            "url": "https://example.com/news",
                            "author": "alice",
                            "created_utc": 1784000000.0,
                            "score": 200,
                            "num_comments": 50,
                            "selftext": "Self text",
                            "permalink": "/r/programming/comments/abc/big_ai_news/",
                        }
                    },
                    {
                        "data": {
                            "id": "def",
                            "title": "Low score filtered",
                            "url": "https://example.com/low",
                            "author": "bob",
                            "created_utc": 1784000000.0,
                            "score": 5,
                            "num_comments": 1,
                            "selftext": "",
                            "permalink": "/r/programming/comments/def/low/",
                        }
                    },
                ]
            }
        }
    )
    src = RedditSource(subreddits=["programming"], min_score=20, rate_limit=10.0)
    items = await src.fetch("AI", hours=24)
    assert len(items) == 1
    item = items[0]
    assert item.source == "reddit"
    assert item.external_id == "abc"
    assert item.metrics["score"] == 200
    assert item.url == "https://example.com/news"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_reddit.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 reddit.py**

`hotspot/sources/reddit.py`:
```python
import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

BASE = "https://www.reddit.com"


@register_source
class RedditSource(BaseSource):
    name = "reddit"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 20,
        rate_limit: float = 1.0,
        **_,
    ):
        self.subreddits = subreddits or ["programming", "MachineLearning", "technology", "artificial"]
        self.min_score = min_score
        self._limiter = RateLimiter(rate_limit)

    async def _search_sub(self, client: httpx.AsyncClient, sub: str, topic: str, hours: int) -> list[Item]:
        params = {
            "q": topic, "sort": "new", "limit": 25,
            "t": "day" if hours <= 24 else "week",
            "restrict_sr": "on",
        }
        await self._limiter.acquire()
        try:
            resp = await client.get(f"{BASE}/r/{sub}/search.json", params=params)
            if resp.status_code == 429:
                return []
            resp.raise_for_status()
        except httpx.HTTPError:
            return []
        data = resp.json().get("data", {}).get("children", [])
        now = datetime.now(timezone.utc)
        items = []
        for c in data:
            d = c.get("data", {})
            if d.get("score", 0) < self.min_score:
                continue
            items.append(Item(
                source=self.name,
                source_type=SourceType.news,
                external_id=d.get("id", ""),
                title=d.get("title", ""),
                url=d.get("url") or f"{BASE}{d.get('permalink', '')}",
                author=d.get("author"),
                published_at=datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc),
                fetched_at=now,
                raw_content=d.get("selftext") or d.get("title", ""),
                metrics={"score": d.get("score", 0), "comments": d.get("num_comments", 0)},
                language="en",
            ))
        return items

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        results: list[Item] = []
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": "hotspot-crawler/0.1"},
        ) as client:
            for sub in self.subreddits:
                results.extend(await self._search_sub(client, sub, topic, hours))
        return results
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_reddit.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/reddit.py tests/test_reddit.py
git commit -m "feat: add Reddit source via public .json endpoints"
```

---

## Task 7: arXiv 适配器

**Files:**
- Create: `hotspot/sources/arxiv.py`
- Create: `tests/test_arxiv.py`

- [ ] **Step 1: 写失败测试**

`tests/test_arxiv.py`:
```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_arxiv.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 arxiv.py**

`hotspot/sources/arxiv.py`:
```python
import httpx
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


@register_source
class ArxivSource(BaseSource):
    name = "arxiv"

    def __init__(self, max_results: int = 50, rate_limit: float = 1.0, **_):
        self.max_results = max_results
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        params = {
            "search_query": f"all:{topic}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(self.max_results),
        }
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            text = resp.text
        root = ET.fromstring(text)
        items = []
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        for entry in root.findall("atom:entry", NS):
            id_url = (entry.findtext("atom:id", default="", namespaces=NS) or "").strip()
            m = re.search(r"arxiv\.org/abs/([^v]+)", id_url)
            ext_id = m.group(1) if m else id_url.split("/")[-1]
            published = entry.findtext("atom:published", default="", namespaces=NS) or ""
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub_dt.timestamp() < cutoff:
                continue
            link = ""
            for l in entry.findall("atom:link", NS):
                if l.get("rel") == "alternate":
                    link = l.get("href") or ""
                    break
            if not link:
                link = id_url
            author_elem = entry.find("atom:author", NS)
            author = author_elem.findtext("atom:name", default=None, namespaces=NS) if author_elem is not None else None
            items.append(Item(
                source=self.name,
                source_type=SourceType.paper,
                external_id=ext_id,
                title=(entry.findtext("atom:title", default="", namespaces=NS) or "").strip(),
                url=link,
                author=author,
                published_at=pub_dt,
                fetched_at=now,
                raw_content=(entry.findtext("atom:summary", default="", namespaces=NS) or "").strip(),
                metrics={},
                language="en",
            ))
        return items
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_arxiv.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/arxiv.py tests/test_arxiv.py
git commit -m "feat: add arXiv source via Atom API"
```

---

## Task 8: GitHub 适配器

**Files:**
- Create: `hotspot/sources/github.py`
- Create: `tests/test_github.py`

- [ ] **Step 1: 写失败测试**

`tests/test_github.py`:
```python
import respx
import pytest
from hotspot.sources.github import GithubSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_repos_filtered_by_stars():
    respx.get("https://api.github.com/search/repositories").respond(
        json={
            "items": [
                {
                    "id": 1, "name": "cool-repo", "full_name": "alice/cool-repo",
                    "html_url": "https://github.com/alice/cool-repo",
                    "description": "A cool repo",
                    "stargazers_count": 500, "forks_count": 50,
                    "language": "Python", "pushed_at": "2026-07-25T10:00:00Z",
                    "owner": {"login": "alice"},
                },
                {
                    "id": 2, "name": "small-repo", "full_name": "bob/small-repo",
                    "html_url": "https://github.com/bob/small-repo",
                    "description": "Too small",
                    "stargazers_count": 10, "forks_count": 1,
                    "language": "Python", "pushed_at": "2026-07-25T10:00:00Z",
                    "owner": {"login": "bob"},
                },
            ]
        }
    )
    src = GithubSource(min_stars=50, token=None, rate_limit=10.0)
    items = await src.fetch("llm", hours=24)
    assert len(items) == 1
    item = items[0]
    assert item.source == "github"
    assert item.source_type.value == "github"
    assert item.external_id == "1"
    assert item.title == "alice/cool-repo"
    assert item.metrics["stars"] == 500
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_github.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 github.py**

`hotspot/sources/github.py`:
```python
import httpx
from datetime import datetime, timezone, timedelta

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API = "https://api.github.com/search/repositories"


@register_source
class GithubSource(BaseSource):
    name = "github"

    def __init__(self, min_stars: int = 50, token: str | None = None, rate_limit: float = 1.0, **_):
        self.min_stars = min_stars
        self.token = token
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d")
        params = {
            "q": f"{topic} in:name,description,readme pushed:>{since} stars:>={self.min_stars}",
            "sort": "stars", "order": "desc", "per_page": 50,
        }
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API, params=params, headers=headers)
            if resp.status_code == 403:
                return []
            resp.raise_for_status()
            data = resp.json()
        items = []
        now = datetime.now(timezone.utc)
        for r in data.get("items", []):
            try:
                pushed = datetime.fromisoformat(r.get("pushed_at", "").replace("Z", "+00:00"))
            except ValueError:
                pushed = now
            items.append(Item(
                source=self.name,
                source_type=SourceType.github,
                external_id=str(r["id"]),
                title=r.get("full_name") or r.get("name") or "",
                url=r.get("html_url") or "",
                author=(r.get("owner") or {}).get("login"),
                published_at=pushed,
                fetched_at=now,
                raw_content=r.get("description") or "",
                metrics={"stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0)},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        owner_repo = item.title
        headers = {"Accept": "application/vnd.github.raw"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner_repo}/readme",
                    headers=headers,
                )
                readme = resp.text if resp.status_code == 200 else ""
            except httpx.HTTPError:
                readme = ""
        parts = [item.raw_content, readme[:8000]]
        return "\n\n".join(p for p in parts if p)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_github.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/github.py tests/test_github.py
git commit -m "feat: add GitHub Search API source with README full-text"
```

---

## Task 9: Medium + Dev.to 适配器

**Files:**
- Create: `hotspot/sources/medium.py`
- Create: `hotspot/sources/devto.py`
- Create: `tests/test_medium.py`
- Create: `tests/test_devto.py`

- [ ] **Step 1: 写 Medium 失败测试**

`tests/test_medium.py`:
```python
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
```

- [ ] **Step 2: 实现 medium.py**

`hotspot/sources/medium.py`:
```python
import httpx
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter


@register_source
class MediumSource(BaseSource):
    name = "medium"

    def __init__(self, min_claps: int = 100, rate_limit: float = 1.0, **_):
        self.min_claps = min_claps
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        url = f"https://medium.com/feed/tag/{topic}"
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
        root = ET.fromstring(text)
        items = []
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        for item in root.findall(".//item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            pub_str = item.findtext("pubDate") or ""
            try:
                pub_dt = parsedate_to_datetime(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if pub_dt.timestamp() < cutoff:
                continue
            desc = (item.findtext("description") or "").strip()
            items.append(Item(
                source=self.name,
                source_type=SourceType.blog,
                external_id=link.split("/")[-1] or link,
                title=title,
                url=link,
                author=item.findtext("author") or item.findtext("dc:creator", default=None, namespaces={"dc": "http://purl.org/dc/elements/1.1/"}),
                published_at=pub_dt,
                fetched_at=now,
                raw_content=desc,
                metrics={},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        await self._limiter.acquire()
        try:
            from trafilatura import fetch_url, extract
            html = fetch_url(item.url)
            if not html:
                return item.raw_content
            text = extract(html, include_comments=False, include_tables=False) or item.raw_content
            return text[:10000]
        except Exception:
            return item.raw_content
```

- [ ] **Step 3: 写 Dev.to 失败测试**

`tests/test_devto.py`:
```python
import respx
import pytest
from hotspot.sources.devto import DevtoSource


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_articles():
    respx.get("https://dev.to/api/articles").respond(
        json=[
            {
                "id": 1, "title": "Article One",
                "url": "https://dev.to/alice/article-one",
                "published_at": "2026-07-25T10:00:00Z",
                "positive_reactions_count": 100,
                "comments_count": 10,
                "description": "First article",
                "user": {"username": "alice"},
                "tag_list": "ai",
            }
        ]
    )
    src = DevtoSource(min_reactions=50, rate_limit=10.0)
    items = await src.fetch("ai", hours=48)
    assert len(items) == 1
    item = items[0]
    assert item.source == "devto"
    assert item.external_id == "1"
    assert item.metrics["reactions"] == 100
```

- [ ] **Step 4: 实现 devto.py**

`hotspot/sources/devto.py`:
```python
import httpx
from datetime import datetime, timezone

from hotspot.models import Item, SourceType
from hotspot.sources import register_source
from hotspot.sources.base import BaseSource, RateLimiter

API = "https://dev.to/api/articles"


@register_source
class DevtoSource(BaseSource):
    name = "devto"

    def __init__(self, min_reactions: int = 50, rate_limit: float = 1.0, **_):
        self.min_reactions = min_reactions
        self._limiter = RateLimiter(rate_limit)

    async def fetch(self, topic: str, hours: int) -> list[Item]:
        params = {"tag": topic, "per_page": 50}
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API, params=params)
            resp.raise_for_status()
            data = resp.json()
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - hours * 3600
        items = []
        for a in data:
            reactions = a.get("positive_reactions_count", 0)
            if reactions < self.min_reactions:
                continue
            try:
                pub = datetime.fromisoformat(a.get("published_at", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub.timestamp() < cutoff:
                continue
            items.append(Item(
                source=self.name,
                source_type=SourceType.blog,
                external_id=str(a.get("id", "")),
                title=a.get("title", ""),
                url=a.get("url", ""),
                author=(a.get("user") or {}).get("username"),
                published_at=pub,
                fetched_at=now,
                raw_content=a.get("description") or "",
                metrics={"reactions": reactions, "comments": a.get("comments_count", 0)},
                language="en",
            ))
        return items

    async def fetch_full(self, item: Item) -> str:
        ext_id = item.external_id
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(f"{API}/{ext_id}")
                if resp.status_code != 200:
                    return item.raw_content
                body = resp.json().get("body_markdown") or item.raw_content
            except httpx.HTTPError:
                return item.raw_content
        return body[:10000]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_medium.py tests/test_devto.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add hotspot/sources/medium.py hotspot/sources/devto.py tests/test_medium.py tests/test_devto.py
git commit -m "feat: add Medium (RSS) and Dev.to (API) sources"
```

---

## Task 10: Ollama 客户端

**Files:**
- Create: `hotspot/llm/__init__.py`
- Create: `hotspot/llm/ollama_client.py`
- Create: `tests/test_ollama_client.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ollama_client.py`:
```python
import respx
import httpx
import pytest
from hotspot.llm.ollama_client import OllamaClient, LLMError


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_returns_dict():
    respx.post("http://localhost:11434/api/chat").respond(
        json={"message": {"content": '{"winner": "A", "reason": "A is fresher"}'}}
    )
    client = OllamaClient(base_url="http://localhost:11434", model="test-model", max_retries=1)
    result = await client.chat_json("prompt")
    assert result == {"winner": "A", "reason": "A is fresher"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_raises_on_invalid_json():
    respx.post("http://localhost:11434/api/chat").respond(
        json={"message": {"content": "not json"}}
    )
    client = OllamaClient(base_url="http://localhost:11434", model="test-model", max_retries=1)
    with pytest.raises(LLMError):
        await client.chat_json("prompt")


@pytest.mark.asyncio
@respx.mock
async def test_batch_chat_json_returns_none_on_failure():
    respx.post("http://localhost:11434/api/chat").mock(
        side_effect=[
            httpx.Response(200, json={"message": {"content": '{"x": 1}'}}),
            httpx.Response(500, text="server error"),
            httpx.Response(500, text="server error"),
        ]
    )
    client = OllamaClient(
        base_url="http://localhost:11434", model="test-model",
        max_retries=1, concurrency=2,
    )
    results = await client.batch_chat_json(["p1", "p2"])
    assert results[0] == {"x": 1}
    assert results[1] is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_ollama_client.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 ollama_client.py**

`hotspot/llm/ollama_client.py`:
```python
import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "batiai/gemma4-12b:q4",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 120,
        max_retries: int = 3,
        concurrency: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(concurrency)

    async def _raw_chat(self, prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError) as e:
                last_exc = e
                wait = 2 ** attempt
                logger.warning(f"Ollama call failed (attempt {attempt+1}): {e}, retry in {wait}s")
                await asyncio.sleep(wait)
        raise LLMError(f"Ollama call failed after {self.max_retries} retries: {last_exc}")

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Failed to parse JSON from LLM output: {text[:200]}")

    async def chat_json(self, prompt: str, schema_hint: str | None = None) -> dict:
        full_prompt = prompt
        if schema_hint:
            full_prompt = f"{prompt}\n\n必须返回符合以下结构的 JSON：\n{schema_hint}"
        async with self._sem:
            text = await self._raw_chat(full_prompt)
        return self._parse_json(text)

    async def batch_chat_json(self, prompts: list[str]) -> list[dict | None]:
        async def one(p: str) -> dict | None:
            try:
                return await self.chat_json(p)
            except LLMError as e:
                logger.warning(f"Batch call failed: {e}")
                return None
        return await asyncio.gather(*[one(p) for p in prompts])

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
```

`hotspot/llm/__init__.py`:
```python
from hotspot.llm.ollama_client import OllamaClient, LLMError
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_ollama_client.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/llm/ tests/test_ollama_client.py
git commit -m "feat: add OllamaClient with JSON mode, retry, batch, concurrency"
```

---

## Task 11: Prompts 模板

**Files:**
- Create: `hotspot/llm/prompts.py`
- Create: `tests/test_prompts.py`

- [ ] **Step 1: 写失败测试**

`tests/test_prompts.py`:
```python
from hotspot.llm.prompts import (
    build_compare_prompt,
    build_cluster_prompt,
    build_suggestion_prompt,
    build_arxiv_relevance_prompt,
    build_summary_prompt,
)


def test_compare_prompt_contains_both_titles():
    p = build_compare_prompt(
        topic="AGI", title_a="A title", content_a="A content",
        title_b="B title", content_b="B content",
    )
    assert "A title" in p
    assert "B title" in p
    assert "A content" in p
    assert "B content" in p
    assert "AGI" in p
    assert "winner" in p.lower()


def test_cluster_prompt_contains_items():
    p = build_cluster_prompt(topic="AGI", items_json='[{"id":"1","title":"x","elo":1200}]')
    assert "AGI" in p
    assert '"id":"1"' in p
    assert "themes" in p.lower()


def test_suggestion_prompt_contains_topic_and_items():
    p = build_suggestion_prompt(
        topic="AGI", theme_name="AGI突破",
        theme_description="desc", items_json='[{"id":"1","title":"x"}]',
    )
    assert "AGI突破" in p
    assert "title" in p.lower()


def test_arxiv_relevance_prompt():
    p = build_arxiv_relevance_prompt(topic="LLM", title="T", abstract="A")
    assert "LLM" in p
    assert "T" in p
    assert "A" in p
    assert "relevant" in p.lower()


def test_summary_prompt():
    p = build_summary_prompt(topic="AGI", title="T", content="C")
    assert "T" in p
    assert "C" in p
    assert "中文" in p
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 prompts.py**

`hotspot/llm/prompts.py`:
```python
"""LLM prompt 模板。所有模板返回纯字符串。"""


def build_compare_prompt(topic: str, title_a: str, content_a: str, title_b: str, content_b: str) -> str:
    return f"""你是科技自媒体选题评估专家。下面是两篇关于「{topic}」的内容，请判断哪篇更适合作为自媒体选题。

【评估维度与权重】
- 新鲜感 30%: 新观点/新突破/新数据，非旧闻翻炒
- 知识增量 30%: 读者获得的新认知量
- 反常识性 20%: 挑战主流认知的程度
- 话题相关度 10%: 与话题契合度
- 传播潜力 10%: 受众广度、争议性、可视觉化

【内容 A】
标题: {title_a}
全文: {content_a}

【内容 B】
标题: {title_b}
全文: {content_b}

【输出 JSON，且仅输出 JSON】
{{"winner": "A" 或 "B", "reason": "一句话理由，≤50字", "a_score": 0到100的整数, "b_score": 0到100的整数}}"""


def build_cluster_prompt(topic: str, items_json: str) -> str:
    return f"""你是科技自媒体选题分析师。以下是关于「{topic}」的高质量候选内容（已按选题价值排序）。
请将它们归纳为 2-5 个主题。

【候选内容 JSON】
{items_json}

【输出 JSON，且仅输出 JSON】
{{
  "themes": [
    {{
      "name": "主题名，10字以内",
      "description": "一句话主题描述",
      "item_ids": ["id1", "id2"],
      "heat_score": 0到100的整数
    }}
  ]
}}"""


def build_suggestion_prompt(topic: str, theme_name: str, theme_description: str, items_json: str) -> str:
    return f"""你是科技自媒体选题策划师。基于以下主题与候选内容，生成 2-3 个具体选题建议。

【话题】{topic}
【主题】{theme_name}
【主题描述】{theme_description}
【候选内容 JSON】
{items_json}

【要求】
1. freshness_tag 必须是 fresh / counter_intuitive / knowledge_dense 三者之一
2. 每个 key_point 必须能从 evidence_ids 对应的 item 中找到支撑
3. title 必须带钩子（反问/数字/反常识结论），15字以内
4. 报告与文案使用中文

【输出 JSON，且仅输出 JSON】
{{
  "suggestions": [
    {{
      "title": "标题",
      "angle": "切入角度",
      "hook": "开头30秒钩子文案",
      "key_points": ["论点1", "论点2", "论点3"],
      "target_audience": "目标受众",
      "visual_hint": "视觉化建议",
      "evidence_ids": ["item_id"],
      "freshness_tag": "fresh|counter_intuitive|knowledge_dense",
      "estimated_value": 0到100的整数
    }}
  ]
}}"""


def build_arxiv_relevance_prompt(topic: str, title: str, abstract: str) -> str:
    return f"""判断以下 arXiv 论文与话题「{topic}」的相关度。

【标题】{title}
【摘要】{abstract}

【输出 JSON，且仅输出 JSON】
{{"relevant": true或false, "relevance_score": 0到100的整数, "reason": "≤30字理由"}}"""


def build_summary_prompt(topic: str, title: str, content: str) -> str:
    return f"""将以下内容压缩为 ≤200 字的中文摘要，保留关键事实与数据。

【话题】{topic}
【标题】{title}
【原文】{content}

【输出 JSON，且仅输出 JSON】
{{"summary": "中文摘要"}}"""
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_prompts.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/llm/prompts.py tests/test_prompts.py
git commit -m "feat: add prompt templates for compare/cluster/suggest/arxiv/summary"
```

---

## Task 12: Elo Rating 纯算法

**Files:**
- Create: `hotspot/pipeline/__init__.py`
- Create: `hotspot/pipeline/elo.py`
- Create: `tests/test_elo.py`

- [ ] **Step 1: 写失败测试**

`tests/test_elo.py`:
```python
from hotspot.pipeline.elo import EloRanker, expected_score, update_elo


def test_expected_score_equal_ratings():
    e = expected_score(1000, 1000)
    assert abs(e - 0.5) < 1e-9


def test_expected_score_higher_rating_favored():
    e = expected_score(1400, 1000)
    assert e > 0.9


def test_update_elo_winner_gains_loser_loses():
    ra, rb = update_elo(1000, 1000, a_wins=True, k=32)
    assert ra > 1000
    assert rb < 1000
    assert ra + rb == 2000


def test_update_elo_upset_bigger_change():
    ra_win, _ = update_elo(1000, 1400, a_wins=True, k=32)
    ra_lose, _ = update_elo(1400, 1000, a_wins=True, k=32)
    gain_upset = ra_win - 1000
    gain_expected = ra_lose - 1400
    assert gain_upset > gain_expected


def test_ranker_initialization():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    assert r.get_elo("a") == 1000
    assert r.get_elo("b") == 1000


def test_ranker_record_match():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    r.record_match("a", "b", winner="a")
    assert r.get_elo("a") > 1000
    assert r.get_elo("b") < 1000


def test_ranker_top_n():
    r = EloRanker(initial=1000, k=32, band=200)
    for x in ["a", "b", "c"]:
        r.add(x)
    r.record_match("a", "b", winner="a")
    r.record_match("a", "c", winner="a")
    top = r.top_n(2)
    assert top[0][0] == "a"
    assert top[0][1] > 1000


def test_ranker_pick_opponents_returns_two_distinct():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    r.set_elo("a", 1100)
    r.set_elo("b", 1500)
    a, b = r.pick_opponents()
    assert a is not None
    assert b is not None
    assert a != b
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_elo.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 elo.py**

`hotspot/pipeline/elo.py`:
```python
import random


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(rating_a: float, rating_b: float, a_wins: bool, k: int = 32) -> tuple[float, float]:
    e_a = expected_score(rating_a, rating_b)
    e_b = 1.0 - e_a
    s_a = 1.0 if a_wins else 0.0
    s_b = 1.0 - s_a
    new_a = rating_a + k * (s_a - e_a)
    new_b = rating_b + k * (s_b - e_b)
    return new_a, new_b


class EloRanker:
    def __init__(self, initial: int = 1000, k: int = 32, band: int = 200):
        self.initial = initial
        self.k = k
        self.band = band
        self._ratings: dict[str, float] = {}

    def add(self, item_id: str) -> None:
        self._ratings.setdefault(item_id, float(self.initial))

    def set_elo(self, item_id: str, elo: float) -> None:
        self._ratings[item_id] = float(elo)

    def get_elo(self, item_id: str) -> float:
        return self._ratings.get(item_id, float(self.initial))

    def record_match(self, a: str, b: str, winner: str) -> None:
        ra = self.get_elo(a)
        rb = self.get_elo(b)
        a_wins = winner == a
        new_a, new_b = update_elo(ra, rb, a_wins=a_wins, k=self.k)
        self._ratings[a] = new_a
        self._ratings[b] = new_b

    def top_n(self, n: int) -> list[tuple[str, float]]:
        return sorted(self._ratings.items(), key=lambda x: x[1], reverse=True)[:n]

    def all_ratings(self) -> dict[str, float]:
        return dict(self._ratings)

    def pick_opponents(self) -> tuple[str, str | None]:
        ids = list(self._ratings.keys())
        if len(ids) < 2:
            return (ids[0] if ids else "", None)
        first = random.choice(ids)
        first_elo = self._ratings[first]
        candidates = [
            x for x in ids
            if x != first and abs(self._ratings[x] - first_elo) <= self.band
        ]
        if not candidates:
            candidates = [x for x in ids if x != first]
        second = random.choice(candidates)
        return first, second
```

`hotspot/pipeline/__init__.py`: 空文件

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_elo.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/pipeline/__init__.py hotspot/pipeline/elo.py tests/test_elo.py
git commit -m "feat: add EloRating algorithm and ranker with band matching"
```

---

## Task 13: Normalize（去重）

**Files:**
- Create: `hotspot/pipeline/normalize.py`
- Create: `tests/test_normalize.py`

- [ ] **Step 1: 写失败测试**

`tests/test_normalize.py`:
```python
from datetime import datetime, timezone
from hotspot.models import Item, SourceType
from hotspot.pipeline.normalize import dedupe_items, normalize_title


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("Hello, World!") == "hello world"
    assert normalize_title("AI: The Future?") == "ai the future"


def make_item(source, ext_id, title, url="https://x.com", metrics=None):
    return Item(
        source=source, source_type=SourceType.news, external_id=ext_id,
        title=title, url=url,
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
        raw_content="", metrics=metrics or {},
    )


def test_dedupe_same_source_same_ext_id_merges():
    a = make_item("hn", "1", "A", metrics={"points": 100})
    a2 = make_item("hn", "1", "A duplicate", metrics={"points": 100})
    result = dedupe_items([a, a2])
    assert len(result) == 1


def test_dedupe_cross_source_same_title_merges():
    a = make_item("hn", "1", "Same Title", url="https://a.com", metrics={"points": 50})
    b = make_item("reddit", "x", "Same Title", url="https://b.com", metrics={"score": 200})
    result = dedupe_items([a, b])
    assert len(result) == 1


def test_dedupe_different_titles_kept():
    a = make_item("hn", "1", "Title A")
    b = make_item("hn", "2", "Title B")
    result = dedupe_items([a, b])
    assert len(result) == 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_normalize.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 normalize.py**

`hotspot/pipeline/normalize.py`:
```python
import re
from hotspot.models import Item


def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _metrics_score(item: Item) -> int:
    m = item.metrics
    return (
        m.get("points", 0) + m.get("score", 0) + m.get("stars", 0)
        + m.get("reactions", 0) + m.get("comments", 0)
    )


def _merge_into(primary: Item, secondary: Item) -> Item:
    alts = primary.metrics.setdefault("alt_urls", [])
    if secondary.url and secondary.url not in alts and secondary.url != primary.url:
        alts.append(secondary.url)
    for k, v in secondary.metrics.items():
        if k == "alt_urls":
            for u in v:
                if u not in alts and u != primary.url:
                    alts.append(u)
            continue
        if k not in primary.metrics or v > primary.metrics.get(k, 0):
            primary.metrics[k] = v
    return primary


def dedupe_items(items: list[Item]) -> list[Item]:
    by_key: dict[tuple[str, str], Item] = {}
    by_title: dict[str, Item] = {}

    for it in items:
        key1 = (it.source, it.external_id)
        if key1 in by_key:
            existing = by_key[key1]
            if _metrics_score(it) > _metrics_score(existing):
                merged = _merge_into(it, existing)
                by_key[key1] = merged
            else:
                _merge_into(existing, it)
            continue
        by_key[key1] = it

        nt = normalize_title(it.title)
        if nt and nt in by_title:
            existing = by_title[nt]
            if _metrics_score(it) > _metrics_score(existing):
                merged = _merge_into(it, existing)
                by_title[nt] = merged
                by_key[(it.source, it.external_id)] = merged
            else:
                _merge_into(existing, it)
        else:
            by_title[nt] = it

    seen_ids = set()
    result = []
    for item in by_key.values():
        if id(item) in seen_ids:
            continue
        seen_ids.add(id(item))
        result.append(item)
    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_normalize.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/pipeline/normalize.py tests/test_normalize.py
git commit -m "feat: add normalize/dedupe with source-id and title-level merging"
```

---

## Task 14: Fetch 调度

**Files:**
- Create: `hotspot/pipeline/fetch.py`
- Create: `tests/test_fetch.py`

- [ ] **Step 1: 写失败测试**

`tests/test_fetch.py`:
```python
import pytest
from datetime import datetime, timezone
from hotspot.pipeline.fetch import run_fetch, run_fulltext
from hotspot.models import Item, SourceType


class FakeSource:
    name = "fake"

    async def fetch(self, topic, hours):
        return [Item(
            source="fake", source_type=SourceType.news, external_id="1",
            title=f"{topic} item", url="https://x.com",
            published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            raw_content="summary", metrics={"points": 10},
        )]

    async def fetch_full(self, item):
        return "FULL TEXT"


class FailingSource:
    name = "fail"

    async def fetch(self, topic, hours):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_run_fetch_invokes_all_sources():
    items, statuses = await run_fetch([FakeSource()], topic="AI", hours=24)
    assert len(items) == 1
    assert items[0].title == "AI item"
    assert len(statuses) == 1
    assert statuses[0].source == "fake"
    assert statuses[0].status == "success"


@pytest.mark.asyncio
async def test_run_fulltext_replaces_full_content():
    item = Item(
        source="fake", source_type=SourceType.news, external_id="1",
        title="x", url="https://x.com",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="summary", metrics={},
    )
    await run_fulltext([item], source_map={"fake": FakeSource()})
    assert item.full_content == "FULL TEXT"


@pytest.mark.asyncio
async def test_run_fetch_records_failure_without_blocking():
    items, statuses = await run_fetch([FakeSource(), FailingSource()], topic="AI", hours=24)
    assert len(items) == 1
    fail_status = [s for s in statuses if s.source == "fail"]
    assert len(fail_status) == 1
    assert fail_status[0].status == "failed"
    assert "boom" in (fail_status[0].error or "")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_fetch.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 fetch.py**

`hotspot/pipeline/fetch.py`:
```python
import asyncio
import logging

from hotspot.models import Item, SourceRunStatus

logger = logging.getLogger(__name__)


async def run_fetch(sources: list, topic: str, hours: int) -> tuple[list[Item], list[SourceRunStatus]]:
    async def _one(src):
        try:
            items = await src.fetch(topic, hours)
            return items, SourceRunStatus(
                source=src.name, status="success",
                fetched_count=len(items), error=None,
            )
        except Exception as e:
            logger.warning(f"Source {src.name} failed: {e}")
            return [], SourceRunStatus(
                source=src.name, status="failed",
                fetched_count=0, error=str(e),
            )

    results = await asyncio.gather(*[_one(s) for s in sources])
    all_items: list[Item] = []
    all_statuses: list[SourceRunStatus] = []
    for items, status in results:
        all_items.extend(items)
        all_statuses.append(status)
    return all_items, all_statuses


async def run_fulltext(items: list[Item], source_map: dict) -> None:
    async def _one(item: Item):
        src = source_map.get(item.source)
        if src is None:
            item.full_content = item.raw_content
            return
        try:
            text = await src.fetch_full(item)
            item.full_content = text
            item.fulltext_failed = False
        except Exception as e:
            logger.warning(f"Fulltext fetch failed for {item.url}: {e}")
            item.full_content = item.raw_content
            item.fulltext_failed = True

    await asyncio.gather(*[_one(i) for i in items])
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_fetch.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/pipeline/fetch.py tests/test_fetch.py
git commit -m "feat: add concurrent fetch dispatcher with fulltext + failure isolation"
```

---

## Task 15: Analyze 阶段

**Files:**
- Create: `hotspot/pipeline/analyze.py`
- Create: `tests/test_analyze.py`

- [ ] **Step 1: 写失败测试**

`tests/test_analyze.py`:
```python
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
async def test_run_comparisons_updates_elo():
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_analyze.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 analyze.py**

`hotspot/pipeline/analyze.py`:
```python
import json
import logging
from datetime import datetime, timezone

from hotspot.models import Item, Theme, Suggestion
from hotspot.pipeline.elo import EloRanker
from hotspot.llm.prompts import (
    build_compare_prompt, build_cluster_prompt, build_suggestion_prompt,
)

logger = logging.getLogger(__name__)


async def run_comparisons(
    items: list[Item], topic: str, client,
    max_comparisons: int, k: int = 32, band: int = 200,
    early_stop_threshold: int = 50,
) -> tuple[EloRanker, list[dict]]:
    ranker = EloRanker(initial=1000, k=k, band=band)
    for it in items:
        ranker.add(it.id)

    comparisons: list[dict] = []
    no_change_count = 0
    last_top10: tuple = tuple(x[0] for x in ranker.top_n(10))

    for i in range(max_comparisons):
        if len(items) < 2:
            break
        a_id, b_id = ranker.pick_opponents()
        if b_id is None:
            break
        a_item = next(x for x in items if x.id == a_id)
        b_item = next(x for x in items if x.id == b_id)
        prompt = build_compare_prompt(
            topic=topic,
            title_a=a_item.title,
            content_a=a_item.full_content or a_item.raw_content,
            title_b=b_item.title,
            content_b=b_item.full_content or b_item.raw_content,
        )
        try:
            result = await client.chat_json(prompt)
        except Exception as e:
            logger.warning(f"Comparison LLM call failed: {e}")
            continue
        winner_id = a_id if result.get("winner", "A") == "A" else b_id
        ranker.record_match(a_id, b_id, winner=winner_id)
        comparisons.append({
            "item_a_id": a_id, "item_b_id": b_id, "winner": winner_id,
            "reason": result.get("reason", ""),
            "a_score": result.get("a_score", 0), "b_score": result.get("b_score", 0),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cur_top10 = tuple(x[0] for x in ranker.top_n(10))
        if cur_top10 == last_top10:
            no_change_count += 1
            if no_change_count >= early_stop_threshold:
                logger.info(f"Early stop after {i+1} comparisons (top10 stable)")
                break
        else:
            no_change_count = 0
            last_top10 = cur_top10

    ratings = ranker.all_ratings()
    for it in items:
        if it.id in ratings:
            it.elo = int(ratings[it.id])
    return ranker, comparisons


async def run_cluster(items: list[Item], topic: str, client) -> list[Theme]:
    if not items:
        return []
    items_json = json.dumps([
        {"id": it.id, "title": it.title, "source": it.source, "elo": it.elo,
         "summary": (it.raw_content or "")[:200]}
        for it in items
    ], ensure_ascii=False)
    prompt = build_cluster_prompt(topic=topic, items_json=items_json)
    try:
        result = await client.chat_json(prompt)
    except Exception as e:
        logger.warning(f"Cluster LLM call failed: {e}")
        return []
    themes = []
    for t in result.get("themes", []):
        try:
            themes.append(Theme(
                name=t.get("name", ""), description=t.get("description", ""),
                item_ids=t.get("item_ids", []), heat_score=int(t.get("heat_score", 0)),
            ))
        except Exception as e:
            logger.warning(f"Bad theme entry: {t}, err: {e}")
    return themes


async def run_suggestions(
    topic: str, theme_name: str, theme_description: str,
    items: list[Item], client,
) -> list[Suggestion]:
    if not items:
        return []
    items_json = json.dumps([
        {"id": it.id, "title": it.title, "url": it.url,
         "content": (it.full_content or it.raw_content)[:3000]}
        for it in items
    ], ensure_ascii=False)
    prompt = build_suggestion_prompt(
        topic=topic, theme_name=theme_name,
        theme_description=theme_description, items_json=items_json,
    )
    try:
        result = await client.chat_json(prompt)
    except Exception as e:
        logger.warning(f"Suggestion LLM call failed: {e}")
        return []
    suggestions = []
    for s in result.get("suggestions", []):
        try:
            suggestions.append(Suggestion(
                title=s.get("title", ""), angle=s.get("angle", ""),
                hook=s.get("hook", ""), key_points=s.get("key_points", []),
                target_audience=s.get("target_audience", ""),
                visual_hint=s.get("visual_hint", ""),
                evidence_ids=s.get("evidence_ids", []),
                freshness_tag=s.get("freshness_tag", "fresh"),
                estimated_value=int(s.get("estimated_value", 0)),
            ))
        except Exception as e:
            logger.warning(f"Bad suggestion entry: {s}, err: {e}")
    return suggestions


def pick_top_k_items(items: list[Item], k: int) -> list[Item]:
    return sorted(items, key=lambda x: x.elo, reverse=True)[:k]
```

注意：测试期望 `comparisons[0]["winner"] == "a"`，由于 winner_id 实际是 a_id（即 "a"），代码 `winner_id = a_id if result.get("winner", "A") == "A" else b_id` 是正确的。

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_analyze.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/pipeline/analyze.py tests/test_analyze.py
git commit -m "feat: add analyze pipeline (Elo comparisons, clustering, suggestions)"
```

---

## Task 16: 报告渲染

**Files:**
- Create: `hotspot/pipeline/render.py`
- Create: `hotspot/pipeline/templates/report.md.j2`
- Create: `tests/test_render.py`

- [ ] **Step 1: 写失败测试**

`tests/test_render.py`:
```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_render.py -v`
Expected: FAIL

- [ ] **Step 3: 创建 Jinja2 模板**

`hotspot/pipeline/templates/report.md.j2`:
```markdown
# {{ meta.topic }} 自媒体选题调研报告

> 生成时间: {{ meta.created_at.isoformat() }} | 时间窗: {{ meta.hours }}h | 候选: {{ meta.item_count }}篇 | 对比: {{ meta.comparison_count }}次 | 耗时: {{ "%.1f"|format(meta.elapsed_sec) }}s
{% if meta.degraded %}
> ⚠️ **降级模式运行**：Ollama 不可达，仅按 metrics 排序，未完成 LLM 评估
{% endif %}

## 一、执行摘要

- 话题：{{ meta.topic }}
- 候选内容：{{ meta.item_count }} 篇
- 对比次数：{{ meta.comparison_count }}
- 主题数：{{ themes|length }}

### 数据源运行状态

| 源 | 状态 | 抓取数 | 错误 |
|---|---|---|---|
{% for s in source_statuses -%}
| {{ s.source }} | {{ s.status }} | {{ s.fetched_count }} | {{ s.error or "" }} |
{% endfor %}

## 二、主题概览

| 主题 | 描述 | 候选数 | 热度 |
|---|---|---|---|
{% for t in themes|sort(attribute='heat_score', reverse=true) -%}
| {{ t.name }} | {{ t.description }} | {{ t.item_ids|length }} | {{ t.heat_score }} |
{% endfor %}

## 三、选题建议

{% for t in themes|sort(attribute='heat_score', reverse=true) %}
### 主题：{{ t.name }}

{% set sugs = suggestions_by_theme.get(t.name, []) %}
{% for s in sugs %}
#### 建议 {{ loop.index }}：{{ s.title }}

- **切入角度**：{{ s.angle }}
- **钩子**：{{ s.hook }}
- **核心论点**：
{% for p in s.key_points %}  - {{ p }}
{% endfor %}
- **目标受众**：{{ s.target_audience }}
- **视觉化建议**：{{ s.visual_hint }}
- **支撑内容**：{{ s.evidence_ids|join(", ") }}
- **标签**：{{ s.freshness_tag }} | 价值分：{{ s.estimated_value }}

{% endfor %}
{% endfor %}

## 四、Top 20 内容排行（Elo 排序）

| 排名 | 标题 | 源 | Elo | URL |
|---|---|---|---|---|
{% for it in top_items -%}
| {{ loop.index }} | {{ it.title }} | {{ it.source }} | {{ it.elo }} | [链接]({{ it.url }}) |
{% endfor %}

## 五、对比观察精选

{% for c in comparison_observations %}
- {{ c.winner }} 胜：{{ c.reason }}
{% endfor %}

## 六、完整候选列表

| 标题 | 源 | Elo | URL |
|---|---|---|---|
{% for it in all_items -%}
| {{ it.title }} | {{ it.source }} | {{ it.elo }} | [链接]({{ it.url }}) |
{% endfor %}

## 附录：运行参数

```json
{{ config_snapshot | tojson(indent=2) }}
```
```

- [ ] **Step 4: 实现 render.py**

`hotspot/pipeline/render.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hotspot.models import Item, Theme, Suggestion, ReportMeta, SourceRunStatus

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ReportContext:
    meta: ReportMeta
    source_statuses: list[SourceRunStatus]
    themes: list[Theme]
    suggestions_by_theme: dict[str, list[Suggestion]]
    top_items: list[Item]
    all_items: list[Item]
    comparison_observations: list[dict]
    config_snapshot: dict


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_report(ctx: ReportContext) -> str:
    template = _env.get_template("report.md.j2")
    return template.render(**ctx.__dict__)
```

- [ ] **Step 5: 运行测试验证通过**

Run: `pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add hotspot/pipeline/render.py hotspot/pipeline/templates/ tests/test_render.py
git commit -m "feat: add Jinja2-based Markdown report rendering"
```

---

## Task 17: SQLite 存储

**Files:**
- Create: `hotspot/storage/__init__.py`
- Create: `hotspot/storage/sqlite_index.py`
- Create: `hotspot/storage/report_files.py`
- Create: `tests/test_sqlite_index.py`

- [ ] **Step 1: 写失败测试**

`tests/test_sqlite_index.py`:
```python
import pytest
from datetime import datetime, timezone
from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.models import ReportMeta, Item, SourceType, SourceRunStatus


@pytest.fixture
def idx(tmp_path):
    return SqliteIndex(tmp_path / "test.db")


def test_init_creates_tables(idx):
    import sqlite3
    conn = sqlite3.connect(idx.db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"reports", "items", "comparisons", "source_runs"} <= tables


def test_save_and_get_report(idx):
    meta = ReportMeta(
        run_id="r1", topic="AI", hours=24,
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        item_count=2, comparison_count=6, elapsed_sec=10.0,
        file_path="reports/x.md",
    )
    idx.save_report(meta)
    got = idx.get_report("r1")
    assert got is not None
    assert got.topic == "AI"
    assert got.file_path == "reports/x.md"


def test_list_reports_ordered_by_time(idx):
    for i, t in enumerate(["2026-07-25T10:00:00+00:00", "2026-07-26T10:00:00+00:00"]):
        idx.save_report(ReportMeta(
            run_id=f"r{i}", topic="AI", hours=24,
            created_at=datetime.fromisoformat(t),
            item_count=1, comparison_count=0, elapsed_sec=1.0,
            file_path=f"x{i}.md",
        ))
    reports = idx.list_reports()
    assert reports[0].run_id == "r1"


def test_save_items_and_comparisons(idx):
    meta = ReportMeta(
        run_id="r1", topic="AI", hours=24,
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        item_count=1, comparison_count=1, elapsed_sec=1.0,
        file_path="x.md",
    )
    idx.save_report(meta)
    item = Item(
        source="hn", source_type=SourceType.news, external_id="1",
        title="T", url="https://x.com",
        published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        raw_content="s", metrics={"points": 10}, elo=1200,
    )
    item.id = "i1"
    idx.save_items("r1", [item])
    items = idx.get_items("r1")
    assert len(items) == 1
    assert items[0].elo == 1200

    idx.save_comparison({
        "run_id": "r1", "item_a_id": "i1", "item_b_id": "i2",
        "winner": "i1", "reason": "x", "a_score": 80, "b_score": 60,
        "created_at": "2026-07-26T12:00:00+00:00",
    })
    comps = idx.get_comparisons("r1")
    assert len(comps) == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_sqlite_index.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 sqlite_index.py**

`hotspot/storage/sqlite_index.py`:
```python
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from hotspot.models import Item, ReportMeta, SourceType, SourceRunStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    hours INTEGER,
    created_at TIMESTAMP,
    item_count INTEGER,
    comparison_count INTEGER,
    elapsed_sec REAL,
    file_path TEXT,
    config_snapshot TEXT,
    degraded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    source TEXT,
    source_type TEXT,
    external_id TEXT,
    title TEXT,
    url TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP,
    metrics TEXT,
    elo INTEGER DEFAULT 1000,
    full_content TEXT,
    summary TEXT,
    fulltext_failed INTEGER DEFAULT 0,
    language TEXT,
    author TEXT
);

CREATE TABLE IF NOT EXISTS comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    item_a_id TEXT,
    item_b_id TEXT,
    winner TEXT,
    reason TEXT,
    a_score INTEGER,
    b_score INTEGER,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_runs (
    run_id TEXT,
    source TEXT,
    status TEXT,
    fetched_count INTEGER,
    error TEXT,
    PRIMARY KEY (run_id, source)
);
"""


class SqliteIndex:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def save_report(self, meta: ReportMeta) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO reports
                   (id, topic, hours, created_at, item_count, comparison_count,
                    elapsed_sec, file_path, config_snapshot, degraded)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    meta.run_id, meta.topic, meta.hours,
                    meta.created_at.isoformat(), meta.item_count,
                    meta.comparison_count, meta.elapsed_sec, meta.file_path,
                    json.dumps(meta.config_snapshot or {}, ensure_ascii=False),
                    1 if meta.degraded else 0,
                ),
            )

    def get_report(self, run_id: str) -> ReportMeta | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM reports WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        return _row_to_meta(row)

    def list_reports(self) -> list[ReportMeta]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
        return [_row_to_meta(r) for r in rows]

    def save_items(self, run_id: str, items: list[Item]) -> None:
        with self._conn() as c:
            for it in items:
                c.execute(
                    """INSERT OR REPLACE INTO items
                       (id, run_id, source, source_type, external_id, title, url,
                        published_at, fetched_at, metrics, elo, full_content,
                        summary, fulltext_failed, language, author)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        it.id, run_id, it.source, it.source_type.value,
                        it.external_id, it.title, it.url,
                        it.published_at.isoformat(), it.fetched_at.isoformat(),
                        json.dumps(it.metrics, ensure_ascii=False), it.elo,
                        it.full_content, it.summary,
                        1 if it.fulltext_failed else 0, it.language, it.author,
                    ),
                )

    def get_items(self, run_id: str) -> list[Item]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM items WHERE run_id=?", (run_id,)).fetchall()
        return [_row_to_item(r) for r in rows]

    def save_comparison(self, comp: dict) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO comparisons
                   (run_id, item_a_id, item_b_id, winner, reason, a_score, b_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    comp["run_id"], comp["item_a_id"], comp["item_b_id"],
                    comp["winner"], comp["reason"], comp.get("a_score", 0),
                    comp.get("b_score", 0), comp.get("created_at"),
                ),
            )

    def get_comparisons(self, run_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM comparisons WHERE run_id=?", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def save_source_run(self, run_id: str, status: SourceRunStatus) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO source_runs
                   (run_id, source, status, fetched_count, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, status.source, status.status, status.fetched_count, status.error),
            )

    def get_source_runs(self, run_id: str) -> list[SourceRunStatus]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM source_runs WHERE run_id=?", (run_id,)).fetchall()
        return [SourceRunStatus(
            source=r["source"], status=r["status"],
            fetched_count=r["fetched_count"], error=r["error"],
        ) for r in rows]


def _row_to_meta(row: sqlite3.Row) -> ReportMeta:
    return ReportMeta(
        run_id=row["id"], topic=row["topic"], hours=row["hours"],
        created_at=datetime.fromisoformat(row["created_at"]),
        item_count=row["item_count"], comparison_count=row["comparison_count"],
        elapsed_sec=row["elapsed_sec"], file_path=row["file_path"],
        degraded=bool(row["degraded"]),
        config_snapshot=json.loads(row["config_snapshot"]) if row["config_snapshot"] else None,
    )


def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"], source=row["source"], source_type=SourceType(row["source_type"]),
        external_id=row["external_id"], title=row["title"], url=row["url"],
        author=row["author"],
        published_at=datetime.fromisoformat(row["published_at"]),
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        raw_content="",
        full_content=row["full_content"],
        metrics=json.loads(row["metrics"]) if row["metrics"] else {},
        elo=row["elo"], language=row["language"],
        fulltext_failed=bool(row["fulltext_failed"]),
        summary=row["summary"],
    )
```

`hotspot/storage/report_files.py`:
```python
import re
from pathlib import Path
from datetime import datetime


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "topic"


def build_report_path(report_dir: str | Path, topic: str, dt: datetime) -> Path:
    name = f"{dt.strftime('%Y-%m-%d-%H%M')}_{slugify(topic)}.md"
    return Path(report_dir) / name


def save_report_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_report_file(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")
```

`hotspot/storage/__init__.py`: 空文件

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_sqlite_index.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/storage/ tests/test_sqlite_index.py
git commit -m "feat: add SQLite index and report file storage"
```

---

## Task 18: CLI 入口

**Files:**
- Create: `hotspot/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner
from hotspot.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "list" in result.stdout
    assert "show" in result.stdout
    assert "web" in result.stdout


def test_list_returns_empty_when_no_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 cli.py**

`hotspot/cli.py`:
```python
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from hotspot.config import load_config
from hotspot.pipeline.fetch import run_fetch, run_fulltext
from hotspot.pipeline.normalize import dedupe_items
from hotspot.pipeline.analyze import (
    run_comparisons, run_cluster, run_suggestions, pick_top_k_items,
)
from hotspot.pipeline.render import render_report, ReportContext
from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.storage.report_files import build_report_path, save_report_file
from hotspot.sources import SOURCE_REGISTRY
from hotspot.llm.ollama_client import OllamaClient

app = typer.Typer(help="hotPoint 热点抓取软件")
console = Console()


@app.command()
def run(
    topic: str = typer.Option(..., "--topic", "-t", help="话题关键词"),
    hours: int = typer.Option(None, "--hours", help="时间窗（小时）"),
    sources: str = typer.Option(None, "--sources", help="逗号分隔的源列表"),
    max_comparisons: int = typer.Option(None, "--max-comparisons", help="对比上限"),
    top_k: int = typer.Option(None, "--top-k", help="进报告的 Top 数"),
    concurrency: int = typer.Option(None, "--concurrency", help="LLM 并发数"),
    model: str = typer.Option(None, "--model", help="Ollama 模型名"),
    no_fulltext: bool = typer.Option(False, "--no-fulltext", help="跳过全文抓取"),
    config_path: str = typer.Option("config.yaml", "--config", help="配置文件路径"),
):
    cfg = load_config(config_path)
    hours = hours or cfg.defaults.hours
    top_k = top_k or cfg.defaults.top_k
    concurrency = concurrency or cfg.defaults.concurrency
    model = model or cfg.llm.model

    enabled_sources = sources.split(",") if sources else [
        s for s, c in cfg.sources.items() if c.enabled
    ]
    source_objs = []
    for name in enabled_sources:
        cls = SOURCE_REGISTRY.get(name.strip())
        if cls is None:
            console.print(f"[yellow]未知源: {name}，跳过[/]")
            continue
        sc = cfg.sources.get(name.strip())
        kwargs = {}
        if sc:
            kwargs = {
                k: v for k, v in sc.model_dump().items()
                if v is not None and k != "enabled"
            }
        source_objs.append(cls(**kwargs))

    if not source_objs:
        console.print("[red]没有可用的数据源[/]")
        raise typer.Exit(1)

    run_id = str(uuid4())
    console.print(f"[cyan]Run ID:[/] {run_id}")
    console.print(f"[cyan]话题:[/] {topic} | 时间窗: {hours}h | 源: {[s.name for s in source_objs]}")

    start = datetime.now(timezone.utc)
    with console.status("[bold green]抓取中..."):
        items, statuses = asyncio.run(run_fetch(source_objs, topic, hours))
    console.print(f"  抓取 {len(items)} 篇")

    items = dedupe_items(items)
    console.print(f"  去重后 {len(items)} 篇")

    if not no_fulltext and items:
        source_map = {s.name: s for s in source_objs}
        with console.status("[bold green]抓取全文..."):
            asyncio.run(run_fulltext(items, source_map))

    client = OllamaClient(
        base_url=cfg.llm.base_url, model=model,
        temperature=cfg.llm.temperature, max_tokens=cfg.llm.max_tokens,
        timeout=cfg.llm.timeout, concurrency=concurrency,
    )
    degraded = False
    comparisons = []
    if items:
        if not asyncio.run(client.ping()):
            console.print("[yellow]⚠️ Ollama 不可达，降级为 metrics 排序[/]")
            degraded = True
            for it in items:
                score = sum(it.metrics.values())
                it.elo = 1000 + score
        else:
            mc = max_comparisons or (len(items) * cfg.defaults.max_comparisons_factor)
            with console.status(f"[bold green]养蛊对比（最多 {mc} 次）..."):
                _, comparisons = asyncio.run(run_comparisons(
                    items, topic=topic, client=client,
                    max_comparisons=mc, k=cfg.elo.k_factor,
                    band=cfg.elo.band, early_stop_threshold=cfg.elo.early_stop_threshold,
                ))
            console.print(f"  完成 {len(comparisons)} 次对比")

    top_items = pick_top_k_items(items, top_k)

    themes = []
    suggestions_by_theme: dict = {}
    if not degraded and top_items:
        with console.status("[bold green]主题聚类..."):
            themes = asyncio.run(run_cluster(top_items, topic=topic, client=client))
        for t in themes:
            theme_items = [i for i in top_items if i.id in t.item_ids][:3]
            if theme_items:
                sugs = asyncio.run(run_suggestions(
                    topic=topic, theme_name=t.name,
                    theme_description=t.description, items=theme_items, client=client,
                ))
                suggestions_by_theme[t.name] = sugs

    end = datetime.now(timezone.utc)
    elapsed = (end - start).total_seconds()
    now = datetime.now(timezone.utc)
    report_path = build_report_path(cfg.report.dir, topic, now)
    meta = __import__("hotspot.models", fromlist=["ReportMeta"]).ReportMeta(
        run_id=run_id, topic=topic, hours=hours, created_at=now,
        item_count=len(items), comparison_count=len(comparisons),
        elapsed_sec=elapsed, file_path=str(report_path),
        degraded=degraded,
        config_snapshot={"llm": {"model": model}, "sources": enabled_sources},
    )
    ctx = ReportContext(
        meta=meta, source_statuses=statuses, themes=themes,
        suggestions_by_theme=suggestions_by_theme, top_items=top_items,
        all_items=items,
        comparison_observations=[c for c in comparisons[:10]],
        config_snapshot=meta.config_snapshot or {},
    )
    md = render_report(ctx)
    save_report_file(report_path, md)

    idx = SqliteIndex(cfg.report.db_path)
    idx.save_report(meta)
    idx.save_items(run_id, items)
    for c in comparisons:
        c_with_run = {**c, "run_id": run_id}
        idx.save_comparison(c_with_run)
    for s in statuses:
        idx.save_source_run(run_id, s)

    console.print(f"[green]✅ 报告已生成:[/] {report_path}")


@app.command(name="list")
def list_reports(
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    reports = idx.list_reports()
    if not reports:
        console.print("[yellow]No reports found.[/]")
        return
    table = Table("Run ID", "话题", "时间", "候选", "对比", "路径")
    for r in reports:
        table.add_row(
            r.run_id[:8], r.topic, r.created_at.strftime("%Y-%m-%d %H:%M"),
            str(r.item_count), str(r.comparison_count), r.file_path,
        )
    console.print(table)


@app.command()
def show(
    run_id: str,
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    meta = idx.get_report(run_id)
    if not meta:
        console.print(f"[red]未找到 run_id: {run_id}[/]")
        raise typer.Exit(1)
    from pathlib import Path
    console.print(Path(meta.file_path).read_text(encoding="utf-8"))


@app.command()
def web(
    port: int = typer.Option(8000, "--port"),
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    import uvicorn
    from hotspot.web.app import create_app
    app_obj = create_app(SqliteIndex(cfg.report.db_path))
    console.print(f"[cyan]启动 Web:[/] http://127.0.0.1:{port}")
    uvicorn.run(app_obj, host="127.0.0.1", port=port, log_level="warning")


@app.command()
def resume(
    run_id: str,
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    meta = idx.get_report(run_id)
    if not meta:
        console.print(f"[red]未找到 run_id: {run_id}[/]")
        raise typer.Exit(1)
    console.print(f"[yellow]resume 功能在 v0.1 暂不支持完整恢复，请重新运行：[/]")
    console.print(f"  hotspot run --topic {meta.topic} --hours {meta.hours}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/cli.py tests/test_cli.py
git commit -m "feat: add Typer CLI with run/list/show/web/resume commands"
```

---

## Task 19: Web UI

**Files:**
- Create: `hotspot/web/__init__.py`
- Create: `hotspot/web/app.py`
- Create: `hotspot/web/static/list.html`
- Create: `hotspot/web/static/style.css`
- Create: `tests/test_web.py`

- [ ] **Step 1: 写失败测试**

`tests/test_web.py`:
```python
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from hotspot.web.app import create_app
from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.models import ReportMeta


@pytest.fixture
def client(tmp_path):
    idx = SqliteIndex(tmp_path / "test.db")
    idx.save_report(ReportMeta(
        run_id="r1", topic="AI", hours=24,
        created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        item_count=10, comparison_count=30, elapsed_sec=10.0,
        file_path="/tmp/x.md",
    ))
    app = create_app(idx)
    return TestClient(app)


def test_list_page_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "AI" in r.text


def test_api_reports_returns_json(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["topic"] == "AI"


def test_api_report_detail(client):
    r = client.get("/api/reports/r1")
    assert r.status_code == 200
    assert r.json()["run_id"] == "r1"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_web.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 app.py**

`hotspot/web/app.py`:
```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import markdown as md

from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.storage.report_files import read_report_file

STATIC_DIR = Path(__file__).parent / "static"


def create_app(idx: SqliteIndex) -> FastAPI:
    app = FastAPI(title="hotPoint Reports")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        reports = idx.list_reports()
        rows = []
        for r in reports:
            rows.append(
                f"<tr><td>{r.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
                f"<td>{r.topic}</td>"
                f"<td>{r.item_count}</td>"
                f"<td>{r.comparison_count}</td>"
                f"<td><a href='/reports/{r.run_id}'>查看</a> "
                f"<a href='/reports/{r.run_id}.md'>md</a></td></tr>"
            )
        html = (STATIC_DIR / "list.html").read_text(encoding="utf-8")
        return html.replace("{{ROWS}}", "\n".join(rows))

    @app.get("/reports/{run_id}", response_class=HTMLResponse)
    def show_report(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        try:
            md_text = read_report_file(meta.file_path)
        except FileNotFoundError:
            raise HTTPException(404, "Report file missing")
        body = md.markdown(md_text, extensions=["tables", "fenced_code"])
        css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        return f"<html><head><meta charset='utf-8'><style>{css}</style></head><body><main>{body}</main></body></html>"

    @app.get("/reports/{run_id}.md", response_class=PlainTextResponse)
    def download_report(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        return read_report_file(meta.file_path)

    @app.get("/api/reports")
    def api_list():
        reports = idx.list_reports()
        return [
            {
                "run_id": r.run_id, "topic": r.topic,
                "created_at": r.created_at.isoformat(),
                "hours": r.hours, "item_count": r.item_count,
                "comparison_count": r.comparison_count,
                "elapsed_sec": r.elapsed_sec, "degraded": r.degraded,
            }
            for r in reports
        ]

    @app.get("/api/reports/{run_id}")
    def api_detail(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        return {
            "run_id": meta.run_id, "topic": meta.topic,
            "created_at": meta.created_at.isoformat(),
            "hours": meta.hours, "item_count": meta.item_count,
            "comparison_count": meta.comparison_count,
            "elapsed_sec": meta.elapsed_sec, "degraded": meta.degraded,
            "file_path": meta.file_path,
        }

    return app
```

`hotspot/web/__init__.py`: 空文件

`hotspot/web/static/list.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>hotPoint 报告列表</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<main>
<h1>hotPoint 报告</h1>
<table>
<thead><tr><th>时间</th><th>话题</th><th>候选</th><th>对比</th><th>操作</th></tr></thead>
<tbody>
{{ROWS}}
</tbody>
</table>
</main>
</body>
</html>
```

`hotspot/web/static/style.css`:
```css
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 2rem; color: #222; }
main { max-width: 900px; margin: 0 auto; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
th { background: #f4f4f4; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_web.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/web/ tests/test_web.py
git commit -m "feat: add FastAPI web UI with report list and detail rendering"
```

---

## Task 20: 端到端集成测试

**Files:**
- Create: `tests/test_pipeline_e2e.py`

- [ ] **Step 1: 写测试**

`tests/test_pipeline_e2e.py`:
```python
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
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/test_pipeline_e2e.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_pipeline_e2e.py
git commit -m "test: add end-to-end pipeline integration test"
```

---

## Task 21: 全量验证

- [ ] **Step 1: 跑全部测试**

Run: `pytest -v`
Expected: 全部 PASS

- [ ] **Step 2: 验证 CLI 可用**

Run: `python -m hotspot --help`
Expected: 显示 run/list/show/web/resume 命令列表

- [ ] **Step 3: 创建 README.md**

```markdown
# hotPoint 热点抓取软件

本地运行的科技自媒体选题调研工具。按话题抓取 6 类英文源（HN/Reddit/arXiv/GitHub/Medium/Dev.to）最近 N 小时热点内容，全文抓取后用 Ollama 本地 LLM 做养蛊式 Elo 对比排序，生成中文自媒体选题调研报告。

## 安装

```bash
python -m pip install -e ".[dev]"
```

## 配置

1. 复制 `.env.example` 为 `.env`，按需填入 `GITHUB_TOKEN`（可选）
2. 确认 Ollama 已启动并加载模型：
   ```bash
   ollama pull batiai/gemma4-12b:q4
   ollama serve
   ```
3. 编辑 `config.yaml` 调整默认参数

## 使用

```bash
python -m hotspot run --topic "AGI" --hours 24
python -m hotspot run --topic "world model" --max-comparisons 50
python -m hotspot list
python -m hotspot show <run_id>
python -m hotspot web --port 8000
```

## 输出

- Markdown 报告：`reports/YYYY-MM-DD-HHmm_<话题>.md`
- SQLite 索引：`hotspot.db`
- Web UI：http://127.0.0.1:8000

## 设计文档

见 `docs/superpowers/specs/2026-07-26-hotspot-crawler-design.md`
```

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: add README with install/config/usage"
```

---

## Self-Review

**1. Spec coverage:**
- 目标与范围 → Task 1-21 全覆盖
- 数据流 → Task 4, 5-9, 14, 15, 16
- 数据模型 → Task 2
- 数据源适配器（6 个源）→ Task 5-9
- 全文抓取 → Task 8 (GitHub README), Task 9 (Medium/Dev.to), Task 14 (调度)
- Elo 养蛊对比排序 → Task 12, 15
- arXiv 二次筛选 → **Gap**: spec 4.3.1 提到但未单独建 Task。补 Task 22。
- 主题聚类与选题建议 → Task 15
- 报告渲染 → Task 16
- CLI → Task 18
- Web UI → Task 19
- 配置 → Task 3
- SQLite → Task 17
- Ollama 客户端 → Task 10
- 错误处理与降级 → Task 10 (LLM), Task 14 (fetch), Task 18 (degraded mode)
- 测试策略 → 每个 Task 都有单测，Task 20 端到端

**2. Placeholder scan:** 无 TBD/TODO，所有步骤都有具体代码。

**3. Type consistency:**
- `Item.id` 在 Task 2 定义为 str，Task 15/17 一致
- `EloRanker.record_match(a, b, winner)` 在 Task 12/15 一致
- `OllamaClient.chat_json(prompt, schema_hint)` 在 Task 10/15 一致
- `run_comparisons` 返回 `(ranker, comparisons)` 在 Task 15 测试与实现一致
- `ReportContext` 字段在 Task 16 测试与 Task 20 一致

**4. 待补 Task 22: arXiv 相关度二次筛选**

---

## Task 22: arXiv 相关度二次筛选

**Files:**
- Modify: `hotspot/sources/arxiv.py` (增加 `filter_by_relevance` 方法)
- Modify: `hotspot/pipeline/fetch.py` (在抓取后调用筛选)
- Create: `tests/test_arxiv_filter.py`

- [ ] **Step 1: 写失败测试**

`tests/test_arxiv_filter.py`:
```python
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_arxiv_filter.py -v`
Expected: FAIL with AttributeError

- [ ] **Step 3: 在 arxiv.py 增加 filter_by_relevance 方法**

在 `ArxivSource` 类中增加：
```python
async def filter_by_relevance(
    self, items: list[Item], topic: str, client,
    min_score: int = 60, concurrency: int = 4,
) -> list[Item]:
    """用 LLM 二次筛选 arXiv 论文相关度。"""
    from hotspot.llm.prompts import build_arxiv_relevance_prompt
    import asyncio

    sem = asyncio.Semaphore(concurrency)

    async def _judge(item: Item) -> tuple[Item, dict | None]:
        prompt = build_arxiv_relevance_prompt(
            topic=topic, title=item.title, abstract=item.raw_content,
        )
        async with sem:
            try:
                return item, await client.chat_json(prompt)
            except Exception:
                return item, None

    results = await asyncio.gather(*[_judge(i) for i in items])
    filtered = []
    for item, result in results:
        if not result:
            continue
        if result.get("relevant") and result.get("relevance_score", 0) >= min_score:
            filtered.append(item)
    return filtered
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_arxiv_filter.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add hotspot/sources/arxiv.py tests/test_arxiv_filter.py
git commit -m "feat: add arXiv relevance filtering via LLM"
```

---

## 执行选择

计划已完成并保存至 `docs/superpowers/plans/2026-07-26-hotspot-crawler.md`。两种执行方式：

**1. Subagent 驱动（推荐）** - 每个 Task 派发一个全新子智能体执行，任务之间进行评审，迭代速度快

**2. 内联执行** - 在当前会话中按任务执行，带检查点的批量执行

请选择哪种方式？
