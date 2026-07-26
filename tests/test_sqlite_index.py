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
