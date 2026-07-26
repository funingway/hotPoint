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
