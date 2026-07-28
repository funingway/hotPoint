# hotPoint · 热点情报终端

本地运行的科技自媒体选题调研工具。按话题抓取多源热点内容（HackerNews / Reddit / arXiv / GitHub / Medium / Dev.to + 任意自定义 RSS/网页），用 **Ollama 本地大模型**做**养蛊式 Elo 两两 PK 排序**，自动聚类生成中文选题调研报告。全程本地、不上云、不订阅。

## 功能特性

- **多源抓取**：6 类内置英文数据源 + 任意自定义 RSS/Atom Feed 或网页
- **全文抓取**：自动获取原文正文（trafilatura + BeautifulSoup4），支持降级回退
- **养蛊式排序**：基于 Elo Rating 的两两对比算法，让大模型当"裁判"两两 PK，band 匹配 + 早停优化
- **LLM 分析**：本地 Ollama 推理，支持 JSON 模式、并发限流、重试降级
- **主题聚类**：自动归纳 2-5 个内容主题，输出热度评分
- **选题建议**：按新鲜感 / 反常识 / 知识增量三维度生成具体选题角度
- **arXiv 二次筛选**：用 LLM 对论文相关度做精细化判断，剔除噪声
- **降级模式**：Ollama 不可达时自动降级为 metrics 排序，保证流水线可用
- **双界面**：Typer CLI（生产用）+ FastAPI Web UI（可视化用）
- **本地存储**：Markdown 报告为真相源，SQLite 作索引
- **实时过程展示**：Web 界面事件流面板，每次 LLM 对比的胜负、分数、理由实时滚动可见
- **随时停止**：任意阶段可点击"停止"按钮中断任务，干净退出
- **一键复制链接**：报告页支持一键复制原文链接到剪贴板

## 快速开始

### Windows 用户（一键启动）

1. 双击 `start.bat`

启动器会自动检测 Python 虚拟环境：
- **已有 `.venv`** → 直接启动 Web 服务
- **无虚拟环境** → 交互提示，选择 `[1]` 一键安装：
  - 自动创建 `.venv` 虚拟环境
  - 安装 `requirements.txt` 全部依赖
  - 检测 Ollama，未安装则自动下载安装包并引导安装
  - 拉取默认模型（`batiai/gemma4-12b:q4`）
  - 完成后自动启动 Web 界面并打开浏览器

### 手动安装（所有平台）

```bash
# 1. 克隆仓库
git clone https://github.com/yourname/hotPoint.git
cd hotPoint

# 2. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装 Ollama 并拉取模型
#    下载地址：https://ollama.com/download
ollama pull batiai/gemma4-12b:q4

# 5. 启动
python start.py
# 或
python -m hotspot web --port 8000
```

要求 Python ≥ 3.10。

### 配置环境变量（可选）

复制 `.env.example` 为 `.env`，按需填入：

```
GITHUB_TOKEN=ghp_xxx  # 提高 GitHub API 速率限制（60/h → 5000/h）
```

## 配置说明

编辑 [config.yaml](config.yaml) 调整默认参数（Web 界面"设置"页可直接在线编辑并保存）：

| 配置块 | 关键字段 | 说明 |
|---|---|---|
| `defaults` | `hours` / `top_k` / `concurrency` | 默认时间窗 / 进报告的 Top 数 / LLM 并发数 |
| `llm` | `base_url` / `model` / `temperature` | Ollama 端点 / 模型名 / 采样温度 |
| `sources` | 每个源的 `enabled` / 阈值参数 | 启用源 + 各源筛选阈值（min_points / min_stars 等） |
| `scoring` | `freshness` / `knowledge_gain` / `counter_intuitive` | LLM 评估维度权重（合计 1.0） |
| `elo` | `initial` / `k_factor` / `band` / `early_stop_threshold` | Elo 初值 / K 因子 / 对手匹配带宽 / 早停阈值 |
| `report` | `dir` / `db_path` | 报告输出目录 / SQLite 索引路径 |
| `custom_sources` | `name` / `url` / `source_type` / `enabled` | 自定义数据源列表（Web 界面管理） |

所有配置均可通过环境变量覆盖，前缀 `HOTSPOT_`，嵌套用 `__` 分隔：

```bash
set HOTSPOT_LLM__MODEL=llama3:8b
set HOTSPOT_DEFAULTS__HOURS=48
```

## 使用方法

### Web 界面（推荐）

```bash
python start.py
# 或
python -m hotspot web --port 8000
```

访问 http://127.0.0.1:8000

| 标签页 | 功能 |
|---|---|
| **搜索** | 输入话题关键词 → 实时查看抓取/对比/聚类全过程 → 查阅报告 |
| **报告档案** | 浏览所有历史报告，点击进入详情 |
| **数据源** | 管理 6 个内置源 + 添加/编辑/删除自定义 RSS/网页源 |
| **设置** | 在线编辑 config.yaml，保存后立即生效 |

**搜索过程面板**包含：
- 进度条 + 阶段提示（抓取 → 去重 → 全文 → 对比 → 聚类 → 选题 → 渲染）
- **事件流**：每次 LLM 对比显示胜方/败方/A 分/B 分/判断理由，按类型分色
- **停止按钮**：随时中断当前任务
- 完成后一键跳转报告页

**报告详情页**包含：
- 顶部 sticky 导航栏：返回主页 / 话题信息 / **复制原文链接** / 下载 .md
- Markdown 渲染：执行摘要、主题概览、选题建议、Top 排行、对比观察

### CLI 命令

```bash
# 抓取并生成报告（核心命令）
python -m hotspot run --topic "AGI" --hours 24
python -m hotspot run --topic "world model" --max-comparisons 50 --top-k 30
python -m hotspot run --topic "LLM agent" --sources hackernews,arxiv,github
python -m hotspot run --topic "RLHF" --no-fulltext          # 跳过全文抓取（更快）
python -m hotspot run --topic "diffusion" --model llama3:8b # 临时切换模型

# 列出所有历史报告
python -m hotspot list

# 查看某次运行的报告内容
python -m hotspot show <run_id>

# 启动 Web 界面
python -m hotspot web --port 8000
```

#### `run` 命令参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--topic / -t` | 话题关键词（必填） | — |
| `--hours` | 时间窗（小时） | 24 |
| `--sources` | 逗号分隔的源列表 | 配置中所有 enabled 的源 |
| `--max-comparisons` | Elo 对比上限 | `items × 3` |
| `--top-k` | 进报告的 Top 数 | 20 |
| `--concurrency` | LLM 并发数 | 4 |
| `--model` | Ollama 模型名 | `batiai/gemma4-12b:q4` |
| `--no-fulltext` | 跳过全文抓取 | False |
| `--config` | 配置文件路径 | `config.yaml` |

## 数据源

### 内置数据源

| 源 | 类型 | API | 筛选阈值 | 全文抓取 |
|---|---|---|---|---|
| HackerNews | news | Official API | `min_points=10` | trafilatura |
| Reddit | news | JSON API | `min_score=20`，可配置 subreddits | trafilatura |
| arXiv | paper | Atom API | 时间窗 + LLM 二次相关度筛选 | 摘要即原文 |
| GitHub | github | REST API | `min_stars=50` | README |
| Medium | blog | RSS | `min_claps=100` | trafilatura |
| Dev.to | blog | API | `min_reactions=50` | 文章正文 |

### 自定义数据源

通过 Web 界面"数据源"标签页添加任意 RSS/Atom Feed 或普通网页：

- **自动检测**：通用 Web 源适配器自动识别 RSS/Atom vs HTML 内容
- **占位符**：URL 中可用 `{topic}` 注入搜索关键词，例如 `https://example.com/search?q={topic}&format=rss`
- **即时生效**：添加后保存到 `config.yaml`，下次搜索即可使用

常见 RSS 路径：`/feed`、`/rss`、`/feed.xml`、`/index.xml`、WordPress `/feed/`、Substack `/feed`、Medium `/feed/tag/{topic}`

扩展内置源：继承 `BaseSource`，实现 `fetch()` 和可选的 `fetch_full()`，用 `@register_source` 装饰器注册。

## LLM 分析引擎

### 评估维度（权重可配置）

| 维度 | 权重 | 说明 |
|---|---|---|
| 新鲜感 freshness | 30% | 新观点 / 新突破 / 新数据，非旧闻翻炒 |
| 知识增量 knowledge_gain | 30% | 读者获得的新认知量 |
| 反常识性 counter_intuitive | 20% | 挑战主流认知的程度 |
| 话题相关度 relevance | 10% | 与话题契合度 |
| 传播潜力 virality | 10% | 受众广度、争议性、可视觉化 |

### 养蛊式 Elo 排序

1. 所有候选内容初始 Elo = 1000
2. 随机挑选两篇（优先 band=200 内的相近 Elo 对手）送 LLM 对比
3. LLM 返回胜者 + 胜负理由，按 K=32 更新双方 Elo
4. 持续对比至达到 `max_comparisons` 或 top10 连续 `early_stop_threshold` 次不变即早停
5. 取 Top K 进报告

Web 界面会实时展示每一次 PK 的结果（胜方/败方/分数/理由），全过程透明。

## 架构设计

```
fetch → normalize → analyze → render → store
 │        │           │          │        │
 │        │           │          │        ├─ Markdown 报告（reports/）
 │        │           │          │        └─ SQLite 索引（hotspot.db）
 │        │           │          │
 │        │           │          └─ Jinja2 模板渲染
 │        │           │
 │        │           ├─ Elo 对比排序（养蛊策略 + 事件回调）
 │        │           ├─ 主题聚类
 │        │           └─ 选题建议生成
 │        │
 │        └─ 标题归一化 + 跨源去重
 │
 └─ 数据源适配器（6 内置 + 通用 Web 源，插件式注册）
```

## 输出

### Markdown 报告

路径：`reports/YYYY-MM-DD-HHmm_<话题slug>.md`

包含章节：
1. 执行摘要（含数据源运行状态表）
2. 主题概览（热度排序）
3. 选题建议（按主题分组，含钩子、论点、视觉化建议）
4. Top 20 内容排行（Elo 排序）
5. 对比观察精选（前 10 次对比理由）
6. 完整候选列表
7. 附录：运行参数

### SQLite 索引

路径：`hotspot.db`，4 张表：
- `reports`：报告元数据
- `items`：内容条目
- `comparisons`：Elo 对比记录
- `source_runs`：数据源运行状态

## 项目结构

```
hotPoint/
├── start.bat                      # Windows 一键启动（最小包装器）
├── start.py                       # 启动器（venv 检测 + 一键安装 + Web 启动）
├── pyproject.toml                 # 项目元数据 + 依赖
├── config.yaml                    # 默认配置
├── requirements.txt               # 运行时依赖
├── .env.example                   # GITHUB_TOKEN 模板
├── hotspot/
│   ├── cli.py                     # Typer CLI（run/list/show/web/resume）
│   ├── config.py                  # pydantic-settings 配置加载
│   ├── models.py                  # Item / Theme / Suggestion / ReportMeta
│   ├── sources/                   # 数据源适配器
│   │   ├── base.py                #   基类 + 注册器
│   │   ├── hackernews.py          #   6 个内置源
│   │   ├── reddit.py / arxiv.py / github.py / medium.py / devto.py
│   │   └── web.py                 #   通用 Web 源（RSS/HTML 自动检测）
│   ├── pipeline/
│   │   ├── fetch.py               # 并发抓取 + 全文调度
│   │   ├── normalize.py           # 标题归一化 + 去重
│   │   ├── analyze.py             # Elo 对比 + 聚类 + 选题（含回调/取消）
│   │   ├── elo.py                 # Elo Rating 纯算法
│   │   ├── render.py              # Jinja2 渲染
│   │   └── templates/report.md.j2
│   ├── llm/
│   │   ├── ollama_client.py       # Ollama 客户端（JSON / 重试 / 并发）
│   │   └── prompts.py             # Prompt 模板
│   ├── storage/
│   │   ├── sqlite_index.py        # SQLite 索引
│   │   └── report_files.py        # 报告文件读写
│   └── web/
│       ├── app.py                 # FastAPI 应用（含事件流 + 任务取消）
│       └── static/                # HTML + CSS
├── reports/                       # 生成的报告（gitignore）
└── tests/                         # 62 个测试（单元 + E2E + Web）
```

## 测试

```bash
# 运行全部测试
python -m pytest -v

# 运行单个模块测试
python -m pytest tests/test_elo.py -v
python -m pytest tests/test_pipeline_e2e.py -v
python -m pytest tests/test_web.py -v
```

测试覆盖：
- 单元测试：每个模块独立测试（elo / normalize / fetch / analyze / render / sqlite / ollama_client / 各源适配器）
- E2E 测试：完整流水线（对比 → 聚类 → 选题 → 渲染）
- Web 测试：FastAPI 端点 + 自定义数据源 CRUD

## 降级与容错

| 故障 | 行为 |
|---|---|
| 某数据源 API 失败 | 跳过该源，记录 `failed` 状态，不影响其他源 |
| 全文抓取失败 | 回退到摘要，标记 `fulltext_failed=True` |
| Ollama 不可达 | 降级为 metrics 排序，报告标记 `degraded=True` |
| LLM 单次对比失败 | 跳过该次对比，继续后续对比 |
| LLM 返回非 JSON | 自动提取 `{...}` 子串解析，仍失败则跳过 |
| 用户点击停止 | 当前步骤完成后干净退出，状态标记 `cancelled` |

## 技术栈

Python 3.10+、Typer、Rich、httpx、Pydantic v2、pydantic-settings、PyYAML、Jinja2、markdown、trafilatura、BeautifulSoup4、FastAPI、uvicorn、Ollama；测试用 pytest + pytest-asyncio + respx。

## 许可证

MIT
