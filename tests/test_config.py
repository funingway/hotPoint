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
