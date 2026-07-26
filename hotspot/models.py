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
