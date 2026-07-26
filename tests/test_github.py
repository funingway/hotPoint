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
