"""hotPoint Web 应用

提供报告浏览、抓取触发、配置管理功能。
抓取在后台线程中运行，通过进度查询接口轮询。
"""
import asyncio
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import markdown as md

from hotspot.config import load_config, AppConfig, CustomSourceConfig
from hotspot.models import ReportMeta
from hotspot.pipeline.fetch import run_fetch, run_fulltext
from hotspot.pipeline.normalize import dedupe_items
from hotspot.pipeline.analyze import (
    run_comparisons, run_cluster, run_suggestions, pick_top_k_items,
)
from hotspot.pipeline.render import render_report, ReportContext
from hotspot.sources import SOURCE_REGISTRY
# 导入所有源模块以触发 @register_source 注册
import hotspot.sources.hackernews  # noqa: F401
import hotspot.sources.reddit      # noqa: F401
import hotspot.sources.arxiv        # noqa: F401
import hotspot.sources.github       # noqa: F401
import hotspot.sources.medium       # noqa: F401
import hotspot.sources.devto        # noqa: F401
import hotspot.sources.web          # noqa: F401
import hotspot.sources.conferences  # noqa: F401
from hotspot.llm.ollama_client import OllamaClient
from hotspot.storage.sqlite_index import SqliteIndex
from hotspot.storage.report_files import build_report_path, save_report_file

STATIC_DIR = Path(__file__).parent / "static"


def _save_custom_sources(config_path: str, cfg: AppConfig,
                         sources_list: list[CustomSourceConfig]) -> None:
    """保存自定义源列表到 config.yaml（保留其他配置）"""
    config_file = Path(config_path)
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["custom_sources"] = [cs.model_dump() for cs in sources_list]
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


# ============================================================
# 抓取任务状态管理（内存中，单实例）
# ============================================================
class RunJob:
    """单次抓取任务的状态。"""
    def __init__(self, run_id: str, topic: str, hours: int):
        self.run_id = run_id
        self.topic = topic
        self.hours = hours
        self.status: str = "pending"        # pending/running/done/failed/cancelled
        self.stage: str = "等待开始"         # 阶段描述
        self.progress: int = 0              # 0-100
        self.error: str | None = None
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.result: dict | None = None
        # 实时事件流（含 LLM 判断结果）
        self.events: list[dict] = []
        self.cancel_requested: bool = False
        self._event_seq = 0
        self._event_lock = threading.Lock()

    def add_event(self, kind: str, message: str = "", **data) -> None:
        """添加一个事件到事件流。

        kind: fetch / dedupe / fulltext / compare / cluster / suggest / render / system / error
        """
        with self._event_lock:
            self._event_seq += 1
            ev = {
                "id": self._event_seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "stage": self.stage,
                "message": message,
            }
            ev.update(data)
            self.events.append(ev)

    def is_cancelled(self) -> bool:
        """供流水线检查的取消钩子。"""
        return self.cancel_requested


class JobManager:
    """管理抓取任务的单例。"""
    def __init__(self):
        self.current: RunJob | None = None
        self._lock = threading.Lock()

    def start(self, topic: str, hours: int, sources: list[str] | None,
              max_comparisons: int | None, top_k: int | None,
              no_fulltext: bool, cfg: AppConfig, idx: SqliteIndex) -> RunJob:
        with self._lock:
            if self.current and self.current.status == "running":
                raise HTTPException(409, "已有任务在运行中，请等待完成")
            run_id = str(uuid4())
            job = RunJob(run_id, topic, hours)
            self.current = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job, topic, hours, sources, max_comparisons,
                  top_k, no_fulltext, cfg, idx),
            daemon=True,
        )
        thread.start()
        return job

    def cancel(self) -> bool:
        """请求取消当前任务。返回是否成功提交请求。"""
        with self._lock:
            if (self.current and self.current.status == "running"
                    and not self.current.cancel_requested):
                self.current.cancel_requested = True
                self.current.add_event(
                    "system", message="用户请求停止，等待当前步骤退出…",
                )
                return True
        return False

    def _run_job(self, job: RunJob, topic: str, hours: int,
                 sources: list[str] | None, max_comparisons: int | None,
                 top_k: int | None, no_fulltext: bool,
                 cfg: AppConfig, idx: SqliteIndex):
        """在后台线程中执行抓取流水线。"""
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            job.status = "running"
            job.add_event("system", message=f"开始任务 · 话题={topic} · 窗口={hours}h")
            try:
                self._pipeline(job, topic, hours, sources, max_comparisons,
                               top_k, no_fulltext, cfg, idx)
            except _CancelledError:
                pass  # 取消已在下面处理
            if job.cancel_requested:
                job.status = "cancelled"
                job.stage = "已停止"
                job.add_event("system", message="任务已停止")
            else:
                job.status = "done"
                job.progress = 100
                job.stage = "完成"
                job.add_event("system", message="任务完成")
        except Exception as e:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.stage = "失败"
            job.add_event("error", message=f"异常: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            job.finished_at = datetime.now(timezone.utc)
            loop.close()

    def _pipeline(self, job: RunJob, topic: str, hours: int,
                  sources: list[str] | None, max_comparisons: int | None,
                  top_k: int | None, no_fulltext: bool,
                  cfg: AppConfig, idx: SqliteIndex):
        """抓取流水线（同步包装异步调用）。"""
        loop = asyncio.get_event_loop()

        def _check_cancel():
            if job.is_cancelled():
                raise _CancelledError()
            return False

        # 阶段 1：构建源
        job.stage = "初始化数据源"
        job.progress = 5
        enabled_sources = sources or [
            s for s, c in cfg.sources.items() if c.enabled
        ]
        # 自动加入启用的自定义源
        custom_enabled = [cs for cs in cfg.custom_sources if cs.enabled]
        if custom_enabled:
            enabled_sources = list(enabled_sources) + [cs.name for cs in custom_enabled]

        source_objs = []
        custom_map = {cs.name: cs for cs in cfg.custom_sources}
        for name in enabled_sources:
            name = name.strip()
            # 自定义源走 WebSource，注入 source_config
            if name in custom_map:
                cs = custom_map[name]
                cls = SOURCE_REGISTRY.get("web")
                if cls is None:
                    continue
                source_objs.append(cls(source_config=cs.model_dump()))
                continue

            cls = SOURCE_REGISTRY.get(name)
            if cls is None:
                continue
            sc = cfg.sources.get(name)
            kwargs = {}
            if sc:
                kwargs = {
                    k: v for k, v in sc.model_dump().items()
                    if v is not None and k != "enabled"
                }
            source_objs.append(cls(**kwargs))

        if not source_objs:
            raise ValueError("没有可用的数据源")

        job.add_event("system", message=f"已加载 {len(source_objs)} 个数据源")

        # 阶段 2：抓取
        job.stage = f"抓取中（{len(source_objs)} 个源）"
        job.progress = 10
        items, statuses = loop.run_until_complete(
            run_fetch(source_objs, topic, hours)
        )
        for s in statuses:
            status_text = "成功" if s.status == "ok" else f"失败({s.error or ''})"
            job.add_event(
                "fetch", message=f"[{s.source}] {s.fetched_count} 条 · {status_text}",
                source=s.source, count=s.fetched_count, status=s.status,
            )
        _check_cancel()

        # 阶段 3：去重
        job.stage = "去重"
        job.progress = 30
        before = len(items)
        items = dedupe_items(items)
        job.add_event(
            "dedupe",
            message=f"去重 {before} → {len(items)}（剔除 {before - len(items)} 篇）",
            before=before, after=len(items),
        )
        _check_cancel()

        # 阶段 4：全文抓取
        if not no_fulltext and items:
            job.stage = "抓取全文"
            job.progress = 40
            source_map = {s.name: s for s in source_objs}
            loop.run_until_complete(run_fulltext(items, source_map))
            ok = sum(1 for it in items if it.full_content)
            fail = sum(1 for it in items if it.fulltext_failed)
            job.add_event(
                "fulltext",
                message=f"全文抓取 成功 {ok} · 失败 {fail} · 跳过 {len(items) - ok - fail}",
                ok=ok, fail=fail,
            )
            _check_cancel()

        # 阶段 5：LLM 分析
        model = cfg.llm.model
        client = OllamaClient(
            base_url=cfg.llm.base_url, model=model,
            temperature=cfg.llm.temperature, max_tokens=cfg.llm.max_tokens,
            timeout=cfg.llm.timeout, concurrency=cfg.defaults.concurrency,
        )
        degraded = False
        comparisons = []

        if items:
            if not loop.run_until_complete(client.ping()):
                degraded = True
                job.add_event(
                    "error",
                    message=f"Ollama 不可达，降级为指标评分（模型={model}）",
                )
                for it in items:
                    score = sum(it.metrics.values()) if it.metrics else 0
                    it.elo = 1000 + score
            else:
                job.add_event("system", message=f"Ollama 就绪 · 模型={model}")
                mc = max_comparisons or (len(items) * cfg.defaults.max_comparisons_factor)
                job.stage = f"养蛊对比（最多 {mc} 次）"
                job.progress = 50

                def _on_compare(i, total, a_item, b_item, winner_item, result):
                    loser = b_item if winner_item.id == a_item.id else a_item
                    reason = (result.get("reason") or "")[:120]
                    job.add_event(
                        "compare",
                        message=f"#{i}/{total} 胜: 「{winner_item.title[:30]}」 "
                                f"败: 「{loser.title[:30]}」 · {reason}",
                        index=i, total=total,
                        winner_title=winner_item.title,
                        winner_url=winner_item.url,
                        loser_title=loser.title,
                        loser_url=loser.url,
                        winner=result.get("winner", "A"),
                        a_score=result.get("a_score", 0),
                        b_score=result.get("b_score", 0),
                        reason=result.get("reason", ""),
                    )
                    # 进度按比例推进 50→72
                    job.progress = 50 + int(22 * i / max(total, 1))

                _, comparisons = loop.run_until_complete(run_comparisons(
                    items, topic=topic, client=client,
                    max_comparisons=mc, k=cfg.elo.k_factor,
                    band=cfg.elo.band, early_stop_threshold=cfg.elo.early_stop_threshold,
                    on_comparison=_on_compare,
                    should_cancel=job.is_cancelled,
                ))
                job.add_event(
                    "system",
                    message=f"对比结束 · 共 {len(comparisons)} 次"
                            + ("（提前停止）" if len(comparisons) < mc else ""),
                )
                _check_cancel()

        # 阶段 6：聚类 + 选题
        top_k = top_k or cfg.defaults.top_k
        top_items = pick_top_k_items(items, top_k)
        job.add_event(
            "system",
            message=f"Top-{top_k} 入选 · Elo 区间 "
                    f"{top_items[-1].elo if top_items else 0}–"
                    f"{top_items[0].elo if top_items else 0}",
        )

        themes = []
        suggestions_by_theme: dict = {}
        if not degraded and top_items and not job.is_cancelled():
            job.stage = "主题聚类"
            job.progress = 75
            themes = loop.run_until_complete(
                run_cluster(top_items, topic=topic, client=client)
            )
            job.add_event(
                "cluster",
                message=f"识别出 {len(themes)} 个主题: "
                        + " / ".join(t.name for t in themes[:5]),
                themes=[{"name": t.name, "score": t.heat_score,
                         "count": len(t.item_ids)} for t in themes],
            )
            _check_cancel()

            job.stage = "生成选题建议"
            job.progress = 85
            for t in themes:
                if job.is_cancelled():
                    break
                theme_items = [i for i in top_items if i.id in t.item_ids][:3]
                if theme_items:
                    sugs = loop.run_until_complete(run_suggestions(
                        topic=topic, theme_name=t.name,
                        theme_description=t.description, items=theme_items, client=client,
                    ))
                    suggestions_by_theme[t.name] = sugs
                    for s in sugs:
                        job.add_event(
                            "suggest",
                            message=f"[{t.name}] 选题: {s.title} "
                                    f"(价值={s.estimated_value} · {s.freshness_tag})",
                            theme=t.name, title=s.title,
                            angle=s.angle, freshness_tag=s.freshness_tag,
                            estimated_value=s.estimated_value,
                        )

        # 阶段 7：渲染 + 存储
        job.stage = "生成报告"
        job.progress = 95
        now = datetime.now(timezone.utc)
        report_path = build_report_path(cfg.report.dir, topic, now)
        meta = ReportMeta(
            run_id=job.run_id, topic=topic, hours=hours, created_at=now,
            item_count=len(items), comparison_count=len(comparisons),
            elapsed_sec=(now - job.started_at).total_seconds(),
            file_path=str(report_path), degraded=degraded,
            config_snapshot={"llm": {"model": model}, "sources": enabled_sources},
        )
        ctx = ReportContext(
            meta=meta, source_statuses=statuses, themes=themes,
            suggestions_by_theme=suggestions_by_theme, top_items=top_items,
            all_items=items,
            comparison_observations=[c for c in comparisons[:10]],
            config_snapshot=meta.config_snapshot or {},
        )
        md_text = render_report(ctx)
        save_report_file(report_path, md_text)

        idx.save_report(meta)
        idx.save_items(job.run_id, items)
        for c in comparisons:
            c_with_run = {**c, "run_id": job.run_id}
            idx.save_comparison(c_with_run)
        for s in statuses:
            idx.save_source_run(job.run_id, s)

        job.result = {
            "run_id": job.run_id,
            "file_path": str(report_path),
            "item_count": len(items),
            "comparison_count": len(comparisons),
            "degraded": degraded,
        }
        job.add_event(
            "render",
            message=f"报告已生成 · {len(items)} 篇 · {len(comparisons)} 次对比",
            path=str(report_path),
        )


class _CancelledError(Exception):
    """用户主动取消任务。"""


# 全局任务管理器
_job_mgr = JobManager()


# ============================================================
# API 模型
# ============================================================
class RunRequest(BaseModel):
    topic: str
    hours: int = 24
    sources: list[str] | None = None
    max_comparisons: int | None = None
    top_k: int | None = None
    no_fulltext: bool = False


class ConfigUpdate(BaseModel):
    config: dict


class CustomSourceRequest(BaseModel):
    """添加/更新自定义源"""
    name: str
    url: str
    source_type: str = "news"  # news / paper / blog / github
    enabled: bool = True


# ============================================================
# FastAPI 应用
# ============================================================
def create_app(idx: SqliteIndex, config_path: str = "config.yaml") -> FastAPI:
    app = FastAPI(title="hotPoint")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---------- 页面 ----------

    @app.get("/", response_class=HTMLResponse)
    def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return html

    @app.get("/reports/{run_id}", response_class=HTMLResponse)
    def show_report(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        try:
            md_text = Path(meta.file_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise HTTPException(404, "Report file missing")
        body = md.markdown(md_text, extensions=["tables", "fenced_code"])
        css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        nav = f"""<nav class="report-nav">
<a href="/" class="report-nav-link">← 返回主页</a>
<div class="report-nav-info">
  <span>话题：<b>{meta.topic}</b></span>
  <span>{meta.created_at.strftime('%Y-%m-%d %H:%M')} UTC</span>
  <span>{meta.item_count} 篇 · {meta.elapsed_sec:.1f}s</span>
</div>
<div class="report-nav-actions">
  <button type="button" class="report-nav-btn" id="copy-link-btn"
          onclick="copyReportLink()" title="复制本页链接">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    <span>复制原文链接</span>
  </button>
  <a href="/reports/{run_id}.md" class="report-nav-link">下载 .md</a>
</div>
</nav>
<script>
function copyReportLink() {{
  const url = window.location.href;
  const btn = document.getElementById('copy-link-btn');
  const label = btn.querySelector('span');
  const done = () => {{
    const old = label.textContent;
    label.textContent = '✓ 已复制';
    btn.classList.add('copied');
    setTimeout(() => {{ label.textContent = old; btn.classList.remove('copied'); }}, 1800);
  }};
  const fail = () => {{
    const old = label.textContent;
    label.textContent = '✕ 失败，请手动复制';
    setTimeout(() => {{ label.textContent = old; }}, 1800);
  }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(url).then(done).catch(() => {{
      // 降级到 execCommand
      const ta = document.createElement('textarea');
      ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try {{ document.execCommand('copy'); done(); }}
      catch (e) {{ fail(); }}
      document.body.removeChild(ta);
    }});
  }} else {{
    const ta = document.createElement('textarea');
    ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try {{ document.execCommand('copy'); done(); }}
    catch (e) {{ fail(); }}
    document.body.removeChild(ta);
  }}
}}
</script>"""
        return f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><style>{css}</style></head><body>{nav}<main class='report-view'>{body}</main></body></html>"

    @app.get("/reports/{run_id}.md", response_class=PlainTextResponse)
    def download_report(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        return Path(meta.file_path).read_text(encoding="utf-8")

    # ---------- 抓取 API ----------

    @app.post("/api/run")
    def api_run(req: RunRequest):
        """触发一次抓取任务（后台运行）。"""
        if not req.topic.strip():
            raise HTTPException(400, "topic 不能为空")
        cfg = load_config(config_path)
        job = _job_mgr.start(
            topic=req.topic.strip(), hours=req.hours,
            sources=req.sources, max_comparisons=req.max_comparisons,
            top_k=req.top_k, no_fulltext=req.no_fulltext,
            cfg=cfg, idx=idx,
        )
        return {"run_id": job.run_id, "status": job.status, "topic": job.topic}

    @app.get("/api/run/status")
    def api_status(since: int = 0):
        """查询当前任务进度。

        since: 客户端上次收到的事件 id，只返回 id > since 的事件（增量）。
        """
        job = _job_mgr.current
        if not job:
            return {"status": "idle", "message": "无任务运行", "events": []}
        with job._event_lock:
            new_events = [ev for ev in job.events if ev["id"] > since]
        return {
            "run_id": job.run_id,
            "topic": job.topic,
            "hours": job.hours,
            "status": job.status,
            "stage": job.stage,
            "progress": job.progress,
            "error": job.error,
            "started_at": job.started_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "result": job.result,
            "events": new_events,
            "last_event_id": job._event_seq,
        }

    @app.post("/api/run/cancel")
    def api_cancel():
        """请求取消当前任务。"""
        ok = _job_mgr.cancel()
        if not ok:
            raise HTTPException(409, "没有可取消的任务")
        return {"status": "ok", "message": "已请求停止任务"}

    # ---------- 报告 API ----------

    @app.get("/api/reports")
    def api_list():
        reports = idx.list_reports()
        return [
            {
                "run_id": r.run_id, "topic": r.topic,
                "created_at": r.created_at.isoformat(),
                "hours": r.hours, "item_count": r.item_count,
                "comparison_count": r.comparison_count,
                "elapsed_sec": r.elapsed_sec, "degraded": r.degraded,
            }
            for r in reports
        ]

    @app.get("/api/reports/{run_id}")
    def api_detail(run_id: str):
        meta = idx.get_report(run_id)
        if not meta:
            raise HTTPException(404, "Report not found")
        items = idx.get_items(run_id)
        return {
            "run_id": meta.run_id, "topic": meta.topic,
            "created_at": meta.created_at.isoformat(),
            "hours": meta.hours, "item_count": meta.item_count,
            "comparison_count": meta.comparison_count,
            "elapsed_sec": meta.elapsed_sec, "degraded": meta.degraded,
            "file_path": meta.file_path,
            "top_items": [
                {
                    "title": i.title, "url": i.url, "source": i.source,
                    "elo": i.elo, "metrics": i.metrics,
                } for i in sorted(items, key=lambda x: -x.elo)[:20]
            ],
        }

    # ---------- 配置 API ----------

    @app.get("/api/config")
    def api_get_config():
        """读取当前配置。"""
        cfg = load_config(config_path)
        return cfg.model_dump()

    @app.post("/api/config")
    def api_save_config(req: ConfigUpdate):
        """保存配置到 config.yaml。"""
        config_file = Path(config_path)
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(req.config, f, allow_unicode=True, sort_keys=False)
        return {"status": "ok", "message": "配置已保存"}

    @app.get("/api/sources")
    def api_sources():
        """列出所有可用的数据源（内置 + 自定义）。"""
        cfg = load_config(config_path)
        builtin = [
            {"name": name, "type": "builtin", "registered": True}
            for name in SOURCE_REGISTRY.keys() if name != "web"
        ]
        custom = [
            {
                "name": cs.name, "type": "custom",
                "url": cs.url, "source_type": cs.source_type,
                "enabled": cs.enabled,
            }
            for cs in cfg.custom_sources
        ]
        return builtin + custom

    # ---------- 自定义源 CRUD ----------

    @app.get("/api/custom-sources")
    def api_list_custom():
        """列出所有自定义源。"""
        cfg = load_config(config_path)
        return [cs.model_dump() for cs in cfg.custom_sources]

    @app.post("/api/custom-sources")
    def api_add_custom(req: CustomSourceRequest):
        """添加或更新自定义源（按 name 去重）。"""
        if not req.name.strip() or not req.url.strip():
            raise HTTPException(400, "name 和 url 不能为空")
        if not req.url.startswith(("http://", "https://")):
            raise HTTPException(400, "url 必须以 http:// 或 https:// 开头")

        cfg = load_config(config_path)
        sources_list = list(cfg.custom_sources)
        # 移除同名旧配置
        sources_list = [cs for cs in sources_list if cs.name != req.name.strip()]
        # 添加新配置
        sources_list.append(CustomSourceConfig(
            name=req.name.strip(),
            url=req.url.strip(),
            source_type=req.source_type,
            enabled=req.enabled,
        ))
        _save_custom_sources(config_path, cfg, sources_list)
        return {"status": "ok", "message": f"自定义源 '{req.name}' 已保存"}

    @app.delete("/api/custom-sources/{name}")
    def api_delete_custom(name: str):
        """删除自定义源。"""
        cfg = load_config(config_path)
        before = len(cfg.custom_sources)
        sources_list = [cs for cs in cfg.custom_sources if cs.name != name]
        if len(sources_list) == before:
            raise HTTPException(404, f"自定义源 '{name}' 不存在")
        _save_custom_sources(config_path, cfg, sources_list)
        return {"status": "ok", "message": f"自定义源 '{name}' 已删除"}

    @app.post("/api/custom-sources/{name}/toggle")
    def api_toggle_custom(name: str):
        """切换自定义源启用状态。"""
        cfg = load_config(config_path)
        sources_list = []
        found = False
        for cs in cfg.custom_sources:
            if cs.name == name:
                sources_list.append(CustomSourceConfig(
                    name=cs.name, url=cs.url,
                    source_type=cs.source_type, enabled=not cs.enabled,
                ))
                found = True
            else:
                sources_list.append(cs)
        if not found:
            raise HTTPException(404, f"自定义源 '{name}' 不存在")
        _save_custom_sources(config_path, cfg, sources_list)
        return {"status": "ok", "message": f"已切换 '{name}' 状态"}

    @app.post("/api/custom-sources/test")
    def api_test_custom(req: CustomSourceRequest):
        """测试自定义源 URL 是否可访问，返回抓取的条目数。"""
        import asyncio
        from hotspot.sources.web import WebSource
        try:
            cs = CustomSourceConfig(
                name=req.name.strip() or "test",
                url=req.url.strip(),
                source_type=req.source_type,
                enabled=True,
            )
            src = WebSource(source_config=cs.model_dump())
            loop = asyncio.new_event_loop()
            try:
                items = loop.run_until_complete(src.fetch(topic="AI", hours=168))
                return {
                    "ok": True,
                    "items_count": len(items),
                    "sample": [
                        {"title": i.title, "url": i.url}
                        for i in items[:3]
                    ],
                }
            finally:
                loop.close()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/ollama/status")
    def api_ollama_status():
        """检查 Ollama 服务状态。"""
        import httpx
        cfg = load_config(config_path)
        try:
            r = httpx.get(f"{cfg.llm.base_url}/api/tags", timeout=2.0)
            if r.status_code == 200:
                tags = r.json()
                models = [m.get("name", "") for m in tags.get("models", [])]
                return {
                    "running": True,
                    "models": models,
                    "model_ready": cfg.llm.model in models,
                }
        except Exception as e:
            return {"running": False, "error": str(e), "models": []}
        return {"running": False, "models": []}

    return app
