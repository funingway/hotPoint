import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from hotspot.config import load_config
from hotspot.models import ReportMeta
from hotspot.pipeline.fetch import run_fetch, run_fulltext
from hotspot.pipeline.normalize import dedupe_items
from hotspot.pipeline.analyze import (
    run_comparisons, run_cluster, run_suggestions, pick_top_k_items,
)
from hotspot.pipeline.render import render_report, ReportContext
from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.storage.report_files import build_report_path, save_report_file
from hotspot.sources import SOURCE_REGISTRY
from hotspot.llm.ollama_client import OllamaClient

app = typer.Typer(help="hotPoint 热点抓取软件")
console = Console()


@app.command()
def run(
    topic: str = typer.Option(..., "--topic", "-t", help="话题关键词"),
    hours: int = typer.Option(None, "--hours", help="时间窗（小时）"),
    sources: str = typer.Option(None, "--sources", help="逗号分隔的源列表"),
    max_comparisons: int = typer.Option(None, "--max-comparisons", help="对比上限"),
    top_k: int = typer.Option(None, "--top-k", help="进报告的 Top 数"),
    concurrency: int = typer.Option(None, "--concurrency", help="LLM 并发数"),
    model: str = typer.Option(None, "--model", help="Ollama 模型名"),
    no_fulltext: bool = typer.Option(False, "--no-fulltext", help="跳过全文抓取"),
    config_path: str = typer.Option("config.yaml", "--config", help="配置文件路径"),
):
    cfg = load_config(config_path)
    hours = hours or cfg.defaults.hours
    top_k = top_k or cfg.defaults.top_k
    concurrency = concurrency or cfg.defaults.concurrency
    model = model or cfg.llm.model

    enabled_sources = sources.split(",") if sources else [
        s for s, c in cfg.sources.items() if c.enabled
    ]
    source_objs = []
    for name in enabled_sources:
        cls = SOURCE_REGISTRY.get(name.strip())
        if cls is None:
            console.print(f"[yellow]未知源: {name}，跳过[/]")
            continue
        sc = cfg.sources.get(name.strip())
        kwargs = {}
        if sc:
            kwargs = {
                k: v for k, v in sc.model_dump().items()
                if v is not None and k != "enabled"
            }
        source_objs.append(cls(**kwargs))

    if not source_objs:
        console.print("[red]没有可用的数据源[/]")
        raise typer.Exit(1)

    run_id = str(uuid4())
    console.print(f"[cyan]Run ID:[/] {run_id}")
    console.print(f"[cyan]话题:[/] {topic} | 时间窗: {hours}h | 源: {[s.name for s in source_objs]}")

    start = datetime.now(timezone.utc)
    with console.status("[bold green]抓取中..."):
        items, statuses = asyncio.run(run_fetch(source_objs, topic, hours))
    console.print(f"  抓取 {len(items)} 篇")

    items = dedupe_items(items)
    console.print(f"  去重后 {len(items)} 篇")

    if not no_fulltext and items:
        source_map = {s.name: s for s in source_objs}
        with console.status("[bold green]抓取全文..."):
            asyncio.run(run_fulltext(items, source_map))

    client = OllamaClient(
        base_url=cfg.llm.base_url, model=model,
        temperature=cfg.llm.temperature, max_tokens=cfg.llm.max_tokens,
        timeout=cfg.llm.timeout, concurrency=concurrency,
    )
    degraded = False
    comparisons = []
    if items:
        if not asyncio.run(client.ping()):
            console.print("[yellow]⚠️ Ollama 不可达，降级为 metrics 排序[/]")
            degraded = True
            for it in items:
                score = sum(it.metrics.values())
                it.elo = 1000 + score
        else:
            mc = max_comparisons or (len(items) * cfg.defaults.max_comparisons_factor)
            with console.status(f"[bold green]养蛊对比（最多 {mc} 次）..."):
                _, comparisons = asyncio.run(run_comparisons(
                    items, topic=topic, client=client,
                    max_comparisons=mc, k=cfg.elo.k_factor,
                    band=cfg.elo.band, early_stop_threshold=cfg.elo.early_stop_threshold,
                ))
            console.print(f"  完成 {len(comparisons)} 次对比")

    top_items = pick_top_k_items(items, top_k)

    themes = []
    suggestions_by_theme: dict = {}
    if not degraded and top_items:
        with console.status("[bold green]主题聚类..."):
            themes = asyncio.run(run_cluster(top_items, topic=topic, client=client))
        for t in themes:
            theme_items = [i for i in top_items if i.id in t.item_ids][:3]
            if theme_items:
                sugs = asyncio.run(run_suggestions(
                    topic=topic, theme_name=t.name,
                    theme_description=t.description, items=theme_items, client=client,
                ))
                suggestions_by_theme[t.name] = sugs

    end = datetime.now(timezone.utc)
    elapsed = (end - start).total_seconds()
    now = datetime.now(timezone.utc)
    report_path = build_report_path(cfg.report.dir, topic, now)
    meta = ReportMeta(
        run_id=run_id, topic=topic, hours=hours, created_at=now,
        item_count=len(items), comparison_count=len(comparisons),
        elapsed_sec=elapsed, file_path=str(report_path),
        degraded=degraded,
        config_snapshot={"llm": {"model": model}, "sources": enabled_sources},
    )
    ctx = ReportContext(
        meta=meta, source_statuses=statuses, themes=themes,
        suggestions_by_theme=suggestions_by_theme, top_items=top_items,
        all_items=items,
        comparison_observations=[c for c in comparisons[:10]],
        config_snapshot=meta.config_snapshot or {},
    )
    md = render_report(ctx)
    save_report_file(report_path, md)

    idx = SqliteIndex(cfg.report.db_path)
    idx.save_report(meta)
    idx.save_items(run_id, items)
    for c in comparisons:
        c_with_run = {**c, "run_id": run_id}
        idx.save_comparison(c_with_run)
    for s in statuses:
        idx.save_source_run(run_id, s)

    console.print(f"[green]✅ 报告已生成:[/] {report_path}")


@app.command(name="list")
def list_reports(
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    reports = idx.list_reports()
    if not reports:
        console.print("[yellow]No reports found.[/]")
        return
    table = Table("Run ID", "话题", "时间", "候选", "对比", "路径")
    for r in reports:
        table.add_row(
            r.run_id[:8], r.topic, r.created_at.strftime("%Y-%m-%d %H:%M"),
            str(r.item_count), str(r.comparison_count), r.file_path,
        )
    console.print(table)


@app.command()
def show(
    run_id: str,
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    meta = idx.get_report(run_id)
    if not meta:
        console.print(f"[red]未找到 run_id: {run_id}[/]")
        raise typer.Exit(1)
    console.print(Path(meta.file_path).read_text(encoding="utf-8"))


@app.command()
def web(
    port: int = typer.Option(8000, "--port"),
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    import uvicorn
    from hotspot.web.app import create_app
    app_obj = create_app(SqliteIndex(cfg.report.db_path), config_path=config_path)
    console.print(f"[cyan]启动 Web:[/] http://127.0.0.1:{port}")
    console.print("[cyan]功能: 抓取触发 / 报告浏览 / 配置管理[/]")
    uvicorn.run(app_obj, host="127.0.0.1", port=port, log_level="warning")


@app.command()
def resume(
    run_id: str,
    config_path: str = typer.Option("config.yaml", "--config"),
):
    cfg = load_config(config_path)
    idx = SqliteIndex(cfg.report.db_path)
    meta = idx.get_report(run_id)
    if not meta:
        console.print(f"[red]未找到 run_id: {run_id}[/]")
        raise typer.Exit(1)
    console.print(f"[yellow]resume 功能在 v0.1 暂不支持完整恢复，请重新运行：[/]")
    console.print(f"  hotspot run --topic {meta.topic} --hours {meta.hours}")


if __name__ == "__main__":
    app()
