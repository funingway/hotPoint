# hotPoint 热点抓取软件 设计规格

> 生成日期: 2026-07-26
> 状态: 待审阅

## 一、目标与范围

### 1.1 目标
为科技自媒体创作者提供一款本地运行的命令行 + Web 工具，按用户设定话题抓取最近 N 小时（默认 24h，可配置）内的全网热点内容（新闻、论文、科技博客、GitHub 项目），自动对内容进行分析判断，最终生成可指导自媒体选题的中文调研报告。

### 1.2 范围
- **运行形态**：CLI 核心工具 + 极简只读 Web 浏览界面
- **数据源**：Hacker News、Reddit、arXiv、GitHub、Medium、Dev.to（6 类英文源）
- **内容语言**：仅抓取英文源；分析报告以中文输出
- **LLM 引擎**：本地 Ollama，模型 `batiai/gemma4-12b:q4`，模型本地路径提示 `D:\openClaw\model`
- **分析策略**：抓取全文 + 养蛊式两两对比排序（Elo Rating）
- **核心输出**：Markdown 调研报告，存档至 `reports/`，SQLite 索引供 Web 浏览

### 1.3 非目标（YAGNI）
- 不抓取社交媒体（Twitter/X、微博、知乎等，需登录或付费 API，抓取不稳定）
- 不做内容发布、推送、定时调度（用户后续可通过 OS 计划任务自行配置）
- 不做用户认证、多用户、云端部署
- 不做向量化检索/RAG（候选量小，LLM 直接处理足够）

## 二、整体架构

### 2.1 数据流

```
[CLI/Web 入口] → [话题 + 时间窗配置]
   → [Source adapters 并发抓取] → [统一 Item 格式]
   → [去重 / 过滤] → [全文抓取]
   → [LLM 养蛊对比排序 (Elo)]
   → [LLM 主题聚类] → [LLM 选题建议生成]
   → [Markdown 渲染] → [reports/ 存档 + SQLite 索引]
   → [Web UI 浏览]
```

### 2.2 目录结构

```
hotPoint/
├── pyproject.toml              # 依赖与项目元数据
├── config.yaml                 # 话题、时间窗、源开关、LLM 配置
├── .env.example                # API token 模板(GitHub 等)
├── hotspot/                    # 主包
│   ├── __init__.py
│   ├── cli.py                  # Typer CLI 入口
│   ├── config.py               # 配置加载(pydantic-settings)
│   ├── models.py               # Item / Report 数据模型(pydantic)
│   ├── sources/                # 数据源适配器
│   │   ├── base.py             # BaseSource 抽象接口
│   │   ├── hackernews.py
│   │   ├── reddit.py
│   │   ├── arxiv.py
│   │   ├── github.py
│   │   ├── medium.py
│   │   └── devto.py
│   ├── pipeline/               # 流水线阶段
│   │   ├── fetch.py            # 并发调度 + 限速 + 全文抓取
│   │   ├── normalize.py        # 标准化 + 去重
│   │   ├── analyze.py          # LLM 评分/聚类/建议
│   │   └── render.py           # Markdown 渲染
│   ├── llm/                    # LLM 客户端封装
│   │   ├── ollama_client.py    # Ollama 调用 + 重试 + 批处理
│   │   └── prompts.py          # 评分/聚类/建议 prompt 模板
│   ├── storage/                # 存储
│   │   ├── sqlite_index.py     # SQLite 元数据索引
│   │   └── report_files.py     # Markdown 文件读写
│   └── web/                    # Web UI
│       ├── app.py              # FastAPI 应用
│       └── static/             # 极简 HTML/CSS(无框架)
├── reports/                    # 生成的报告存放处
└── tests/                      # 单测
```

### 2.3 关键设计原则
- 每个源/流水线阶段独立可测，互不依赖内部实现
- `config.yaml` 控制一切：话题、时间窗、各源开关与参数、LLM 模型名/路径
- 报告文件与 SQLite 索引分离：文件是真相源，SQLite 仅加速 Web 列表
- 单点故障不阻塞整体流程，逐级降级

## 三、数据模型

### 3.1 统一 Item 模型（`models.py`）

```python
class SourceType(str, Enum):
    news = "news"
    paper = "paper"
    blog = "blog"
    github = "github"

class Item(BaseModel):
    id: str                      # uuid
    source: str                  # "hackernews" / "arxiv" / ...
    source_type: SourceType
    external_id: str             # 源站内唯一 ID，用于去重
    title: str
    url: str
    author: str | None
    published_at: datetime
    fetched_at: datetime
    raw_content: str             # 摘要/首段，用于初筛与 LLM 上下文压缩
    full_content: str | None     # 全文，养蛊对比用
    metrics: dict                # points/comments/stars/forks 等
    language: str = "en"
    elo: int = 1000              # 初始 Elo
    fulltext_failed: bool = False
    summary: str | None = None   # LLM 生成的中文摘要
```

## 四、数据源适配器与抓取策略

### 4.1 统一接口（`sources/base.py`）

```python
class BaseSource(ABC):
    name: str

    @abstractmethod
    async def fetch(self, topic: str, hours: int) -> list[Item]:
        """按话题和时间窗抓取，返回标准化 Item 列表"""

    async def fetch_full(self, item: Item) -> str:
        """获取单篇全文，子类可覆写。默认返回 raw_content"""
```

### 4.2 各源策略

| 源 | API | 过滤逻辑 | 全文获取 | 字符上限 |
|---|---|---|---|---|
| Hacker News | Algolia Search API（`https://hn.algolia.com/api/v1/search`） | `query=topic` + `created_at_i>{now-hours*3600}`，points≥10 | 外站正文用 `trafilatura` 抽取 | 8000 |
| Reddit | 公开 `.json` 端点（避免 OAuth） | 搜 r/programming,r/MachineLearning,r/technology,r/artificial；score≥20 | selftext + 高赞评论 Top5 | 8000 |
| arXiv | Atom API（`http://export.arxiv.org/api/query`） | `search_query=all:{topic}` + `sortBy=submittedDate`；LLM 二次筛选相关度 | HTML 版或 ar5iv，PDF 转 txt | 12000 |
| GitHub | Search API（`/search/repositories?q=topic:{x}+pushed:>{date}`） | stars≥50 且近期有 push | README.md raw + description + release notes | 8000 |
| Medium | RSS（`https://medium.com/feed/tag/{topic}`） | 时间窗内，claps≥100（如可获取） | `trafilatura` 抽正文 | 10000 |
| Dev.to | API（`https://dev.to/api/articles?tag={topic}`） | positive_reactions≥50 | `trafilatura` 抽正文 | 10000 |

### 4.3 全文抓取细节
- 统一用 `trafilatura` 抽取正文（对科技文章友好，优于 readability）
- **超长压缩策略**：单篇全文 > 8000 字符时，取前 6000 字 + 调 LLM 生成 ≤2000 字摘要拼接为最终 `full_content`；≤8000 字符直接使用
- 全文存入 `Item.full_content`，与 `raw_content`（摘要）分离
- 失败时退化为摘要，标记 `fulltext_failed=true`

### 4.3.1 arXiv 相关度二次筛选
arXiv 无原生热度指标，按以下流程处理：
1. Atom API 按时间窗取最近 `max_results`（默认 50）篇
2. 对每篇用 LLM 做单次相关度判断（输入标题+摘要），输出 `relevant: bool` + `relevance_score: 0-100`
3. 仅保留 `relevant=true` 且 `relevance_score≥60` 的进入候选池
4. 该步骤的 LLM 调用走 `OllamaClient.chat_json`，并发 4，prompt 见 `prompts.py` 的 `arxiv_relevance`

### 4.4 抓取调度（`pipeline/fetch.py`）
- `asyncio.gather` 并发所有源，每源内部串行分页
- 每源独立 `RateLimiter`（令牌桶），默认 1 req/s
- 单源失败不阻塞其他源，记入 `source_runs` 表
- 网络层用 `httpx.AsyncClient`，统一 UA、超时 30s、重试 3 次（指数退避）

### 4.5 去重逻辑（`pipeline/normalize.py`）
- 一级：`source + external_id` 完全相同 → 直接合并 metrics
- 二级：标题归一化（小写、去标点、去域名）后 SimHash/简单模糊匹配 → 跨源重复合并，保留 metrics 最高者，URL 全部保留

## 五、养蛊式对比排序算法（核心）

### 5.1 算法选择
采用 **Elo Rating 系统**：比单败淘汰更公平，可并行、可中断、可收敛、可续跑。

### 5.2 流程

```
初始化: 每篇 Item 初始 Elo = 1000
对比池: 所有候选 Item（去重后通过初筛的）
预算: M = N * 3 次（N=候选数，可在 config 调，默认每篇平均被对比 3 次）

循环 M 次（可并发）:
    随机抽 2 篇 Elo 接近的（±200 内，找不到则任意）
    构造对比 prompt → 调 LLM
    LLM 输出: winner + a_score + b_score + reason
    更新 Elo:
        E_A = 1 / (1 + 10^((R_B - R_A) / 400))
        R_A += K * (S_A - E_A),  R_B += K * (S_B - E_B)
        K = 32（标准值，可配）

最终: 按 Elo 降序 → Top N 进报告
```

### 5.3 评分维度与权重
LLM 判断"哪篇更值得做成自媒体选题"，依据：
1. **新鲜感**（30%）：新观点/新突破/新数据，非旧闻翻炒
2. **知识增量**（30%）：读者获得的新认知量
3. **反常识性**（20%）：挑战主流认知的程度
4. **话题相关度**（10%）：与话题契合度
5. **传播潜力**（10%）：受众广度、争议性、可视觉化程度

### 5.4 对比 Prompt 模板（`prompts.py`）

```
你是科技自媒体选题评估专家。下面是两篇关于「{topic}」的内容，请判断哪篇更适合作为自媒体选题。

【评估维度与权重】
- 新鲜感 30%: 新观点/新突破/新数据，非旧闻翻炒
- 知识增量 30%: 读者获得的新认知量
- 反常识性 20%: 挑战主流认知的程度
- 话题相关度 10%: 与话题契合度
- 传播潜力 10%: 受众广度、争议性、可视觉化

【内容 A】
标题: {title_a}
全文: {full_content_a}

【内容 B】
标题: {title_b}
全文: {full_content_b}

【输出 JSON】
{{"winner": "A" | "B", "reason": "一句话理由（≤50字）", "a_score": 0-100, "b_score": 0-100}}
```

### 5.5 工程细节
- 并发：`asyncio.gather` 批量对比，默认并发 4（本地模型吞吐有限，避免 OOM）
- 容错：LLM 输出解析失败 → 该次对比作废，不更新 Elo，重试 1 次
- 复用：每次对比的 `reason` 累积存档，最后聚合进报告"对比观察"小节
- 中断恢复：Elo 状态实时写 SQLite（`comparisons` 表），中断后可续跑
- 早期终止：连续 50 次对比 Top 10 排名无变化 → 提前结束，省预算

### 5.6 预算估算
- 候选 N=100 篇 → M=300 次对比
- 单次输入 ≈ 2 × 8000 字 ≈ 16k tokens
- 总输入 ≈ 4.8M tokens，本地模型约 30-60 分钟跑完
- 提供 `--max-comparisons` CLI 参数可临时缩减预算

## 六、主题聚类与选题建议

### 6.1 主题聚类
**输入**：Elo Top 20 篇 Item（含全文/摘要）
**方法**：直接让 LLM 做归纳式聚类（候选量小，无需向量化）

**Prompt 输出 JSON**
```json
{
  "themes": [
    {
      "name": "主题名（10字内）",
      "description": "一句话描述",
      "item_ids": ["id1", "id2"],
      "heat_score": 0-100
    }
  ]
}
```

`heat_score` 基于该主题 Item 数量和 Elo 均值。

### 6.2 选题角度建议
**输入**：每个主题 + 该主题下 Top 3 Item 的全文
**每个主题生成 2-3 个选题建议**，结构如下：

```json
{
  "title": "建议的视频标题（带钩子，15字内）",
  "angle": "切入角度",
  "hook": "开头30秒钩子文案",
  "key_points": ["核心论点1", "核心论点2", "核心论点3"],
  "target_audience": "目标受众画像",
  "visual_hint": "可视觉化建议",
  "evidence_ids": ["支撑该选题的item_id列表"],
  "freshness_tag": "fresh/counter_intuitive/knowledge_dense 三选一",
  "estimated_value": 0-100
}
```

**Prompt 设计要点**
- 强调"新鲜感/知识增量/反常识"三标签必选其一
- 要求每个 key_point 必须能追溯到 evidence_ids（防止 LLM 编造）
- title 要求带钩子（反问/数字/反常识结论）
- 视觉化建议为后期视频制作提供方向

## 七、报告渲染

### 7.1 文件
- 路径：`reports/{YYYY-MM-DD-HHmm}_{话题slug}.md`
- 渲染：Jinja2 模板，模板文件放 `hotspot/pipeline/templates/report.md.j2`
- 同时写入 `reports/` 目录 + SQLite 索引

### 7.2 Markdown 结构

```markdown
# {话题} 自媒体选题调研报告
> 生成时间: {timestamp} | 时间窗: {hours}h | 候选: {N}篇 | 对比: {M}次

## 一、执行摘要
- 抓取总量、各源贡献、Top 主题概述
- 数据源运行状态表（成功/失败/限流）

## 二、主题概览
（聚类结果，按 heat_score 排序）
| 主题 | 描述 | 候选数 | 热度 |

## 三、选题建议（核心）
### 主题1：xxx
#### 建议 1.1：{title}
- 切入角度 / 钩子 / 核心论点 / 目标受众 / 视觉化 / 支撑内容 / 标签 / 价值分

## 四、Top 20 内容排行（Elo 排序）
| 排名 | 标题 | 源 | Elo | 新鲜感 | 知识增量 | 反常识 | URL |

## 五、对比观察精选
（从养蛊对比中挑 10 条最有信息量的 reason）

## 六、完整候选列表
（所有候选 Item 的标题/源/URL/Elo/简短摘要，供人工二次筛选）

## 附录：运行参数
- config 快照、LLM 模型、对比次数、耗时
```

## 八、CLI 设计

### 8.1 命令（基于 Typer）

```bash
# 抓取并生成报告（主命令）
python -m hotspot run --topic "AGI" --hours 24

# 指定数据源
python -m hotspot run --topic "embodied AI" --hours 12 --sources hackernews,arxiv,github

# 限制养蛊对比预算
python -m hotspot run --topic "world model" --max-comparisons 50

# 仅列出历史报告
python -m hotspot list

# 查看某报告
python -m hotspot show <report_id>

# 启动 Web 浏览界面
python -m hotspot web --port 8000

# 续跑上次中断的任务
python -m hotspot resume <run_id>
```

### 8.2 核心参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--topic` | 必填 | 话题关键词 |
| `--hours` | 24 | 时间窗 |
| `--sources` | 全部 | 逗号分隔的源列表 |
| `--max-comparisons` | N×3 | 养蛊对比上限 |
| `--top-k` | 20 | 进报告的 Top 数 |
| `--concurrency` | 4 | LLM 并发数 |
| `--model` | 从 config 读 | Ollama 模型名 |
| `--no-fulltext` | False | 跳过全文抓取（快速模式） |

进度反馈用 `rich` 显示实时进度条。

## 九、Web UI

### 9.1 路由（`web/app.py`）
```
GET /                    # 报告列表页
GET /reports/{id}        # 单报告详情（渲染 Markdown）
GET /api/reports         # JSON 报告列表
GET /api/reports/{id}    # JSON 报告元数据
GET /reports/{id}.md     # 原始 Markdown 下载
```

### 9.2 实现
- 极简只读界面，FastAPI 托管静态 HTML，无前端框架
- 列表页：表格展示 `[时间 | 话题 | 候选数 | 对比次数 | 查看链接]`，按时间倒序
- 详情页：服务端用 `markdown` 库渲染 HTML，套简洁 CSS
- 部署：`python -m hotspot web` 启动 uvicorn，仅监听 127.0.0.1

## 十、配置文件（`config.yaml`）

```yaml
defaults:
  hours: 24
  top_k: 20
  max_comparisons_factor: 3
  concurrency: 4

llm:
  base_url: "http://localhost:11434"
  model: "batiai/gemma4-12b:q4"
  model_path: "D:\\openClaw\\model"   # 提示性，Ollama 实际从其管理路径加载
  temperature: 0.3
  max_tokens: 4096
  timeout: 120

sources:
  hackernews:
    enabled: true
    min_points: 10
    rate_limit: 1.0
  reddit:
    enabled: true
    subreddits: ["programming", "MachineLearning", "technology", "artificial"]
    min_score: 20
  arxiv:
    enabled: true
    max_results: 50
  github:
    enabled: true
    min_stars: 50
    token_env: "GITHUB_TOKEN"
  medium:
    enabled: true
    min_claps: 100
  devto:
    enabled: true
    min_reactions: 50

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
```

配置加载用 `pydantic-settings`，支持 YAML + 环境变量覆盖。

## 十一、存储（SQLite 索引）

### 11.1 Schema

```sql
CREATE TABLE reports (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    hours INTEGER,
    created_at TIMESTAMP,
    item_count INTEGER,
    comparison_count INTEGER,
    elapsed_sec REAL,
    file_path TEXT,
    config_snapshot TEXT
);

CREATE TABLE items (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES reports(id),
    source TEXT, source_type TEXT,
    external_id TEXT, title TEXT, url TEXT,
    published_at TIMESTAMP, fetched_at TIMESTAMP,
    metrics TEXT,
    elo INTEGER DEFAULT 1000,
    full_content TEXT,
    summary TEXT
);

CREATE TABLE comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, item_a_id TEXT, item_b_id TEXT,
    winner TEXT, reason TEXT,
    a_score INTEGER, b_score INTEGER,
    created_at TIMESTAMP
);

CREATE TABLE source_runs (
    run_id TEXT, source TEXT,
    status TEXT,
    fetched_count INTEGER, error TEXT,
    PRIMARY KEY (run_id, source)
);
```

## 十二、LLM 客户端（`llm/ollama_client.py`）

### 12.1 能力
- 封装 Ollama `/api/chat` 接口（对比任务用非流式批量）
- **JSON 模式**：所有 LLM 调用要求结构化 JSON 输出，用 `format: "json"` 参数 + prompt 约束
- **重试**：网络错误重试 3 次（指数退避 1s/2s/4s）；JSON 解析失败重试 1 次
- **并发控制**：`asyncio.Semaphore(concurrency)`，默认 4
- **超时**：单次 120s，可配
- **降级**：若 Ollama 不可达，对比任务降级为"按 metrics 排序"并标记 `degraded=true`

### 12.2 接口

```python
class OllamaClient:
    async def chat_json(
        self, prompt: str, schema_hint: str | None = None
    ) -> dict:
        """调用 LLM 返回 JSON dict，失败抛 LLMError"""

    async def batch_chat_json(
        self, prompts: list[str]
    ) -> list[dict | None]:
        """批量并发调用，单条失败返回 None"""
```

## 十三、错误处理与降级策略

| 故障点 | 策略 |
|---|---|
| 单数据源失败 | 跳过该源，报告"数据源状态"标注失败原因 |
| 全文抓取失败 | 退化为摘要，Item 标记 `fulltext_failed=true` |
| Ollama 不可达 | 整体降级为 metrics 排序，报告顶部红色警示 |
| LLM 单次对比解析失败 | 该次对比作废，重试 1 次仍失败则跳过 |
| 全部对比都失败 | 报告仅输出 Top by metrics，标注"未完成 LLM 评估" |
| 网络超时 | 重试 3 次后跳过该 Item |

## 十四、测试策略

- **单元测试**：每个源适配器 mock HTTP 响应测解析；Elo 更新算法测数值正确性；prompt 模板渲染测变量替换
- **集成测试**：用 `respx` mock 全部 HTTP 调用 + `MockOllamaClient` 返回固定 JSON，跑完整流水线验证报告生成
- **不测**：真实网络、真实 Ollama（CI 跑不了）

## 十五、依赖清单（`pyproject.toml`）

```toml
[project]
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "httpx>=0.27",
    "pydantic>=2",
    "pydantic-settings>=2",
    "pyyaml>=6",
    "jinja2>=3",
    "markdown>=3",
    "trafilatura>=1.12",
    "beautifulsoup4>=4.12",
    "python-dateutil>=2.9",
    "fastapi>=0.110",
    "uvicorn>=0.30",
]
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21"]
```

## 十六、关键决策记录

1. **采用 Elo 而非单败淘汰**：可并行、可中断、可续跑、对小样本更鲁棒
2. **抓全文而非仅摘要**：用户明确要求，养蛊对比需要完整上下文判断
3. **仅英文源**：论文与 GitHub 几乎全英文，且前沿信息一手；中文源噪声大且抓取不稳定
4. **本地 Ollama**：用户指定，零调用成本、隐私好；接受本地 GPU 算力约束
5. **不用向量化聚类**：Top 20 候选量小，LLM 直接归纳更准且简单
6. **报告文件 + SQLite 双写**：文件为真相源便于版本管理与导出，SQLite 加速 Web 浏览
7. **Reddit 走公开 .json 端点**：避免 OAuth 复杂度，被限流时降级跳过
