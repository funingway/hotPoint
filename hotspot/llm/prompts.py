"""LLM prompt 模板。所有模板返回纯字符串。"""


def build_compare_prompt(topic: str, title_a: str, content_a: str, title_b: str, content_b: str) -> str:
    return f"""你是科技自媒体选题评估专家。下面是两篇关于「{topic}」的内容，请判断哪篇更适合作为自媒体选题。

【评估维度与权重】
- 新鲜感 30%: 新观点/新突破/新数据，非旧闻翻炒
- 知识增量 30%: 读者获得的新认知量
- 反常识性 20%: 挑战主流认知的程度
- 话题相关度 10%: 与话题契合度
- 传播潜力 10%: 受众广度、争议性、可视觉化

【内容 A】
标题: {title_a}
全文: {content_a}

【内容 B】
标题: {title_b}
全文: {content_b}

【输出 JSON，且仅输出 JSON】
{{"winner": "A" 或 "B", "reason": "一句话理由，≤50字", "a_score": 0到100的整数, "b_score": 0到100的整数}}"""


def build_cluster_prompt(topic: str, items_json: str) -> str:
    return f"""你是科技自媒体选题分析师。以下是关于「{topic}」的高质量候选内容（已按选题价值排序）。
请将它们归纳为 2-5 个主题。

【候选内容 JSON】
{items_json}

【输出 JSON，且仅输出 JSON】
{{
  "themes": [
    {{
      "name": "主题名，10字以内",
      "description": "一句话主题描述",
      "item_ids": ["id1", "id2"],
      "heat_score": 0到100的整数
    }}
  ]
}}"""


def build_suggestion_prompt(topic: str, theme_name: str, theme_description: str, items_json: str) -> str:
    return f"""你是科技自媒体选题策划师。基于以下主题与候选内容，生成 2-3 个具体选题建议。

【话题】{topic}
【主题】{theme_name}
【主题描述】{theme_description}
【候选内容 JSON】
{items_json}

【要求】
1. freshness_tag 必须是 fresh / counter_intuitive / knowledge_dense 三者之一
2. 每个 key_point 必须能从 evidence_ids 对应的 item 中找到支撑
3. title 必须带钩子（反问/数字/反常识结论），15字以内
4. 报告与文案使用中文

【输出 JSON，且仅输出 JSON】
{{
  "suggestions": [
    {{
      "title": "标题",
      "angle": "切入角度",
      "hook": "开头30秒钩子文案",
      "key_points": ["论点1", "论点2", "论点3"],
      "target_audience": "目标受众",
      "visual_hint": "视觉化建议",
      "evidence_ids": ["item_id"],
      "freshness_tag": "fresh|counter_intuitive|knowledge_dense",
      "estimated_value": 0到100的整数
    }}
  ]
}}"""


def build_arxiv_relevance_prompt(topic: str, title: str, abstract: str) -> str:
    return f"""判断以下 arXiv 论文与话题「{topic}」的相关度。

【标题】{title}
【摘要】{abstract}

【输出 JSON，且仅输出 JSON】
{{"relevant": true或false, "relevance_score": 0到100的整数, "reason": "≤30字理由"}}"""


def build_summary_prompt(topic: str, title: str, content: str) -> str:
    return f"""将以下内容压缩为 ≤200 字的中文摘要，保留关键事实与数据。

【话题】{topic}
【标题】{title}
【原文】{content}

【输出 JSON，且仅输出 JSON】
{{"summary": "中文摘要"}}"""
