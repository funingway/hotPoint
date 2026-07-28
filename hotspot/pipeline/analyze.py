import json
import logging
from datetime import datetime, timezone

from hotspot.models import Item, Theme, Suggestion
from hotspot.pipeline.elo import EloRanker
from hotspot.llm.prompts import (
    build_compare_prompt, build_cluster_prompt, build_suggestion_prompt,
)

logger = logging.getLogger(__name__)


async def run_comparisons(
    items: list[Item], topic: str, client,
    max_comparisons: int, k: int = 32, band: int = 200,
    early_stop_threshold: int = 50,
    on_comparison=None, should_cancel=None,
) -> tuple[EloRanker, list[dict]]:
    """养蛊式 Elo 对比。

    on_comparison: 可选回调 (i, max_comparisons, a_item, b_item, winner_item, result_dict)
    should_cancel: 可选无参回调，返回 True 时立即停止。
    """
    ranker = EloRanker(initial=1000, k=k, band=band)
    for it in items:
        ranker.add(it.id)

    comparisons: list[dict] = []
    no_change_count = 0
    last_top10: tuple = tuple(x[0] for x in ranker.top_n(10))

    for i in range(max_comparisons):
        if len(items) < 2:
            break
        if should_cancel and should_cancel():
            logger.info("Comparisons cancelled by user")
            break
        a_id, b_id = ranker.pick_opponents()
        if b_id is None:
            break
        a_item = next(x for x in items if x.id == a_id)
        b_item = next(x for x in items if x.id == b_id)
        prompt = build_compare_prompt(
            topic=topic,
            title_a=a_item.title,
            content_a=a_item.full_content or a_item.raw_content,
            title_b=b_item.title,
            content_b=b_item.full_content or b_item.raw_content,
        )
        try:
            result = await client.chat_json(prompt)
        except Exception as e:
            logger.warning(f"Comparison LLM call failed: {e}")
            continue
        winner_id = a_id if result.get("winner", "A") == "A" else b_id
        winner_item = a_item if winner_id == a_id else b_item
        ranker.record_match(a_id, b_id, winner=winner_id)
        comparisons.append({
            "item_a_id": a_id, "item_b_id": b_id, "winner": winner_id,
            "reason": result.get("reason", ""),
            "a_score": result.get("a_score", 0), "b_score": result.get("b_score", 0),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        if on_comparison:
            try:
                on_comparison(i + 1, max_comparisons,
                              a_item, b_item, winner_item, result)
            except Exception as cb_err:
                logger.warning(f"on_comparison callback error: {cb_err}")
        cur_top10 = tuple(x[0] for x in ranker.top_n(10))
        if cur_top10 == last_top10:
            no_change_count += 1
            if no_change_count >= early_stop_threshold:
                logger.info(f"Early stop after {i+1} comparisons (top10 stable)")
                break
        else:
            no_change_count = 0
            last_top10 = cur_top10

    ratings = ranker.all_ratings()
    for it in items:
        if it.id in ratings:
            it.elo = int(ratings[it.id])
    return ranker, comparisons


async def run_cluster(items: list[Item], topic: str, client) -> list[Theme]:
    if not items:
        return []
    items_json = json.dumps([
        {"id": it.id, "title": it.title, "source": it.source, "elo": it.elo,
         "summary": (it.raw_content or "")[:200]}
        for it in items
    ], ensure_ascii=False)
    prompt = build_cluster_prompt(topic=topic, items_json=items_json)
    try:
        result = await client.chat_json(prompt)
    except Exception as e:
        logger.warning(f"Cluster LLM call failed: {e}")
        return []
    themes = []
    for t in result.get("themes", []):
        try:
            themes.append(Theme(
                name=t.get("name", ""), description=t.get("description", ""),
                item_ids=t.get("item_ids", []), heat_score=int(t.get("heat_score", 0)),
            ))
        except Exception as e:
            logger.warning(f"Bad theme entry: {t}, err: {e}")
    return themes


async def run_suggestions(
    topic: str, theme_name: str, theme_description: str,
    items: list[Item], client,
) -> list[Suggestion]:
    if not items:
        return []
    items_json = json.dumps([
        {"id": it.id, "title": it.title, "url": it.url,
         "content": (it.full_content or it.raw_content)[:3000]}
        for it in items
    ], ensure_ascii=False)
    prompt = build_suggestion_prompt(
        topic=topic, theme_name=theme_name,
        theme_description=theme_description, items_json=items_json,
    )
    try:
        result = await client.chat_json(prompt)
    except Exception as e:
        logger.warning(f"Suggestion LLM call failed: {e}")
        return []
    suggestions = []
    for s in result.get("suggestions", []):
        try:
            suggestions.append(Suggestion(
                title=s.get("title", ""), angle=s.get("angle", ""),
                hook=s.get("hook", ""), key_points=s.get("key_points", []),
                target_audience=s.get("target_audience", ""),
                visual_hint=s.get("visual_hint", ""),
                evidence_ids=s.get("evidence_ids", []),
                freshness_tag=s.get("freshness_tag", "fresh"),
                estimated_value=int(s.get("estimated_value", 0)),
            ))
        except Exception as e:
            logger.warning(f"Bad suggestion entry: {s}, err: {e}")
    return suggestions


def pick_top_k_items(items: list[Item], k: int) -> list[Item]:
    return sorted(items, key=lambda x: x.elo, reverse=True)[:k]
