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


class CustomSourceConfig(BaseModel):
    """用户自定义 Web 数据源"""
    name: str
    url: str
    source_type: str = "news"  # news / paper / blog / github
    enabled: bool = True


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
    custom_sources: list[CustomSourceConfig] = []


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
