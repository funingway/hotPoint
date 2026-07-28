import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from hotspot.web.app import create_app, _job_mgr
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
    # 重置任务管理器状态
    _job_mgr.current = None
    # 用临时配置文件
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
defaults:
  hours: 24
  top_k: 20
  max_comparisons_factor: 3
  concurrency: 2
llm:
  base_url: "http://localhost:11434"
  model: "batiai/gemma4-12b:q4"
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
    app = create_app(idx, config_path=str(config_path))
    return TestClient(app)


def test_index_page_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "hotPoint" in r.text
    assert "热点脉搏" in r.text
    assert "run-form" in r.text


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


def test_api_sources(client):
    r = client.get("/api/sources")
    assert r.status_code == 200
    sources = r.json()
    names = [s["name"] for s in sources]
    assert "hackernews" in names


def test_api_run_status_idle(client):
    r = client.get("/api/run/status")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"


def test_api_run_rejects_empty_topic(client):
    r = client.post("/api/run", json={"topic": "  "})
    assert r.status_code == 400


def test_api_config_get(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["defaults"]["hours"] == 24
    assert cfg["llm"]["model"] == "batiai/gemma4-12b:q4"


def test_api_config_save(client, tmp_path):
    cfg = client.get("/api/config").json()
    cfg["defaults"]["hours"] = 48
    r = client.post("/api/config", json={"config": cfg})
    assert r.status_code == 200
    # 验证已写入文件
    import yaml
    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert saved["defaults"]["hours"] == 48


def test_api_custom_sources_crud(client):
    """测试自定义源 CRUD 全流程"""
    # 初始为空
    r = client.get("/api/custom-sources")
    assert r.status_code == 200
    assert r.json() == []

    # 添加
    r = client.post("/api/custom-sources", json={
        "name": "techcrunch",
        "url": "https://techcrunch.com/feed/",
        "source_type": "news",
        "enabled": True,
    })
    assert r.status_code == 200

    # 列表
    r = client.get("/api/custom-sources")
    sources = r.json()
    assert len(sources) == 1
    assert sources[0]["name"] == "techcrunch"
    assert sources[0]["url"] == "https://techcrunch.com/feed/"

    # 切换启用状态
    r = client.post("/api/custom-sources/techcrunch/toggle")
    assert r.status_code == 200
    r = client.get("/api/custom-sources")
    assert r.json()[0]["enabled"] is False

    # 删除
    r = client.delete("/api/custom-sources/techcrunch")
    assert r.status_code == 200
    r = client.get("/api/custom-sources")
    assert r.json() == []


def test_api_custom_sources_validation(client):
    """测试自定义源 URL 校验"""
    # 缺 URL
    r = client.post("/api/custom-sources", json={
        "name": "test", "url": "", "source_type": "news",
    })
    assert r.status_code == 400

    # URL 格式错误
    r = client.post("/api/custom-sources", json={
        "name": "test", "url": "not-a-url", "source_type": "news",
    })
    assert r.status_code == 400


def test_api_sources_includes_custom(client):
    """测试 /api/sources 同时返回内置和自定义源"""
    client.post("/api/custom-sources", json={
        "name": "myblog",
        "url": "https://blog.example.com/feed",
        "source_type": "blog",
        "enabled": True,
    })
    r = client.get("/api/sources")
    sources = r.json()
    types = [s.get("type") for s in sources]
    assert "builtin" in types
    assert "custom" in types
