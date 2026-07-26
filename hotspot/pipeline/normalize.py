import re
from hotspot.models import Item


def normalize_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _metrics_score(item: Item) -> int:
    m = item.metrics
    return (
        m.get("points", 0) + m.get("score", 0) + m.get("stars", 0)
        + m.get("reactions", 0) + m.get("comments", 0)
    )


def _merge_into(primary: Item, secondary: Item) -> Item:
    alts = primary.metrics.setdefault("alt_urls", [])
    if secondary.url and secondary.url not in alts and secondary.url != primary.url:
        alts.append(secondary.url)
    for k, v in secondary.metrics.items():
        if k == "alt_urls":
            for u in v:
                if u not in alts and u != primary.url:
                    alts.append(u)
            continue
        if k not in primary.metrics or v > primary.metrics.get(k, 0):
            primary.metrics[k] = v
    return primary


def dedupe_items(items: list[Item]) -> list[Item]:
    # Use a single canonical map keyed by the preferred item, with two indexes
    # pointing into the same Item objects.
    canonical: list[Item] = []
    by_key: dict[tuple[str, str], Item] = {}
    by_title: dict[str, Item] = {}

    def _replace(old: Item, new: Item) -> None:
        # Swap old -> new in both indexes
        for k, v in list(by_key.items()):
            if v is old:
                by_key[k] = new
        for k, v in list(by_title.items()):
            if v is old:
                by_title[k] = new
        # Replace in canonical list
        idx = canonical.index(old)
        canonical[idx] = new

    for it in items:
        key1 = (it.source, it.external_id)
        existing_by_key = by_key.get(key1)
        if existing_by_key is not None:
            if _metrics_score(it) > _metrics_score(existing_by_key):
                _merge_into(it, existing_by_key)
                _replace(existing_by_key, it)
            else:
                _merge_into(existing_by_key, it)
            continue

        nt = normalize_title(it.title)
        existing_by_title = by_title.get(nt) if nt else None
        if existing_by_title is not None:
            if _metrics_score(it) > _metrics_score(existing_by_title):
                _merge_into(it, existing_by_title)
                _replace(existing_by_title, it)
            else:
                _merge_into(existing_by_title, it)
            continue

        # New item, add to all indexes
        canonical.append(it)
        by_key[key1] = it
        if nt:
            by_title[nt] = it

    return canonical
