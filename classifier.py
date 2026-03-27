"""
classifier.py – Phân loại bài viết theo keyword + AI fallback
"""

import logging
from marketreview import (
    INTL_KEYWORDS, VN_KEYWORDS,
    VN_MARKET_EVENING_KEYWORDS, INTL_ENERGY_RATES_EVENING_KEYWORDS,
)

log = logging.getLogger(__name__)


# ── Keyword matching ──────────────────────────────────────────────────────────
def _score(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)

def _classify_article(article: dict, keyword_map: dict[str, list[str]]) -> str | None:
    text = f"{article['title']} {article['summary']}".lower()
    best_group, best_score = None, 0
    for group, keywords in keyword_map.items():
        score = _score(text, keywords)
        if score > best_score:
            best_score = score
            best_group = group
    return best_group if best_score > 0 else None


# ── Morning classifier (8 nhóm) ───────────────────────────────────────────────
def classify_morning(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Phân bài vào 8 nhóm morning:
    - intl_war, intl_energy, intl_fed, intl_global_fin (bài tiếng Anh)
    - vn_rates, vn_infra, vn_domestic_fin, vn_corporate  (bài tiếng Việt)
    Bài không phân loại được đưa vào 'unclassified'.
    """
    buckets: dict[str, list[dict]] = {
        "intl_war":         [],
        "intl_energy":      [],
        "intl_fed":         [],
        "intl_global_fin":  [],
        "vn_rates":         [],
        "vn_infra":         [],
        "vn_domestic_fin":  [],
        "vn_corporate":     [],
        "unclassified":     [],
    }
    for a in articles:
        if a.get("lang") == "vi":
            group = _classify_article(a, VN_KEYWORDS)
        else:
            group = _classify_article(a, INTL_KEYWORDS)
        if group and group in buckets:
            buckets[group].append(a)
        else:
            buckets["unclassified"].append(a)

    for grp, arts in buckets.items():
        log.info("Morning [%s]: %d bài", grp, len(arts))
    return buckets


# ── Evening classifier (6 nhóm) ───────────────────────────────────────────────
def classify_evening(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Phân bài vào 6 nhóm evening:
    - vn_market, vn_rates, vn_infra, vn_corporate (bài tiếng Việt)
    - intl_war, intl_energy_rates              (bài tiếng Anh)
    """
    intl_keyword_map = {
        "intl_war":           INTL_KEYWORDS["intl_war"],
        "intl_energy_rates":  INTL_ENERGY_RATES_EVENING_KEYWORDS,
    }
    vn_keyword_map = {
        "vn_market":    VN_MARKET_EVENING_KEYWORDS,
        "vn_rates":     VN_KEYWORDS["vn_rates"],
        "vn_infra":     VN_KEYWORDS["vn_infra"],
        "vn_corporate": VN_KEYWORDS["vn_corporate"],
    }

    buckets: dict[str, list[dict]] = {
        "vn_market":          [],
        "vn_rates":           [],
        "vn_infra":           [],
        "vn_corporate":       [],
        "intl_war":           [],
        "intl_energy_rates":  [],
        "unclassified":       [],
    }
    for a in articles:
        if a.get("lang") == "vi":
            group = _classify_article(a, vn_keyword_map)
        else:
            group = _classify_article(a, intl_keyword_map)
        if group and group in buckets:
            buckets[group].append(a)
        else:
            buckets["unclassified"].append(a)

    for grp, arts in buckets.items():
        log.info("Evening [%s]: %d bài", grp, len(arts))
    return buckets
