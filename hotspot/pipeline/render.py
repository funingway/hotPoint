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
