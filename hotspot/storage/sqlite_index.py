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
