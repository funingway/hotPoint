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
