from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_SCORED_PATH = OUT_DIR / "posts_scored.jsonl"
POSTS_SCORED_SAMPLE_PATH = OUT_DIR / "posts_scored_sample.jsonl"
COMPANY_TOPIC_FEATURES_PATH = OUT_DIR / "company_topic_features.jsonl"
COMPANY_TOPIC_FEATURES_SAMPLE_PATH = OUT_DIR / "company_topic_features_sample.jsonl"
TOPIC_SUMMARY_PATH = OUT_DIR / "comment_topic_summary.json"
TOPIC_SUMMARY_SAMPLE_PATH = OUT_DIR / "comment_topic_summary_sample.json"
COMMENT_ESG_FEATURES_PATH = OUT_DIR / "company_comment_esg_features.jsonl"
COMMENT_ESG_FEATURES_SAMPLE_PATH = OUT_DIR / "company_comment_esg_features_sample.jsonl"
COMMENT_ESG_SUMMARY_PATH = OUT_DIR / "comment_esg_axes_summary.json"
COMMENT_ESG_SUMMARY_SAMPLE_PATH = OUT_DIR / "comment_esg_axes_summary_sample.json"

URL_RE = re.compile(r"https?://\S+")
DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|co|ai|gov|edu|biz|info|me|ca|uk|de|fr|jp|cn|ly|gg)\b(?:/\S*)?",
    re.IGNORECASE,
)
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9\.\-]*")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
NON_WORD_RE = re.compile(r"[^a-z\s]")
MULTISPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z]{3,}")

GENERIC_TOPIC_TERMS = {
    "add", "added", "ago", "article", "articles", "better", "big", "bounce", "bought", "bull",
    "buying", "close", "com", "comment", "days", "dip", "dips", "dont", "easy", "end", "finally",
    "fuck", "fuckin", "going", "gonna", "good", "got", "great", "guess", "guys", "happened",
    "happens", "hard", "higher", "hope", "hours", "interesting", "just", "know", "let", "lets",
    "like", "linkedin", "list", "loading", "look", "looking", "looks", "love", "low", "maybe",
    "money", "month", "months", "move", "moving", "need", "net", "nice", "org", "people", "pick",
    "play", "pop", "press", "ready", "really", "release", "releases", "right", "roll", "room",
    "run", "running", "seekingalpha", "selling", "shit", "small", "sold", "soon", "squeeze",
    "started", "starting", "stocksrunner", "stocktitan", "stuff", "sure", "thing", "things",
    "thought", "time", "tipranks", "undervalued", "wait", "waiting", "want", "watchlist", "way",
    "week", "weeks", "wow", "www", "wtf", "yahoo", "alert", "signal", "stockinvest", "pivotpoint",
    "contracts", "contract", "premium", "strike", "exp", "upside", "massive", "huge", "range",
    "tight", "bit", "little", "best", "far", "forget", "miss", "don", "doesn", "didn", "goes",
    "monday", "friday", "yesterday", "today", "tomorrow", "lot", "point", "points", "continue",
    "caps", "ooc", "pre", "otc", "tsx", "investing", "weeks", "month", "months", "potential",
}
DOMAIN_HINT_TERMS = {
    "article", "articles", "com", "finance", "gov", "investors", "linkedin", "newsfilecorp", "org",
    "press", "release", "releases", "seekingalpha", "sec", "stocktitan", "stocksrunner", "tipranks",
    "www", "yahoo",
}
NOISY_TOPIC_TERMS = {
    "briefing", "mergerbrief", "newsfile", "newsfilecorp", "newswire", "otcmarkets", "otcstocks",
    "otcmarketscom", "otcqb", "otcqx", "otcpk", "quarterlyresults", "stockhouse", "thefly", "tmx",
    "tsx", "tsxv", "nfne", "ws", "globenewswire",
}
NOISY_TOPIC_PATTERNS = (
    "otcmarkets",
    "otcstocks",
    "quarterlyresults",
    "newswire",
    "mergerbrief",
    "briefing.com",
    "globenewswire",
    "newsfile",
    "stockhouse",
    "tsx",
    "tmx",
    "nfne",
)
TOPIC_DOC_STOPWORDS = set(ENGLISH_STOP_WORDS).union(
    {
        "bullish", "bearish", "market", "price", "stock", "stocks", "trade", "trading", "share",
        "shares", "today", "tomorrow", "position", "positions", "watch", "watching",
    }
)




NON_NORMATIVE_BLUEPRINTS = [
    {
        "label": "Earnings and guidance",
        "summary": "Czysto rynkowy motyw wynikow, guidance i oczekiwan analitykow.",
        "descriptor": "earnings revenue eps guidance yoy beat miss consensus estimate quarter annual forecast",
        "keywords": ["earnings", "revenue", "eps", "guidance", "consensus"],
    },
    {
        "label": "Price action and trading setup",
        "summary": "Motyw techniczny i tradingowy bez wyraznego znaczenia normatywnego.",
        "descriptor": "breakout support resistance chart swing trade volume setup target stop momentum bounce dip",
        "keywords": ["breakout", "support", "resistance", "chart", "volume"],
    },
    {
        "label": "Dividend valuation returns",
        "summary": "Motyw wyceny, dywidendy i dochodu inwestora.",
        "descriptor": "dividend yield valuation multiple upside downside return payout re rating undervalued overvalued",
        "keywords": ["dividend", "yield", "valuation", "payout", "return"],
    },
    {
        "label": "Deal and speculative flow",
        "summary": "M and A, rumor, takeover i spekulacyjne katalizatory niebedace ESG-like same w sobie.",
        "descriptor": "deal merger acquisition rumor bid catalyst squeeze partnership speculation",
        "keywords": ["deal", "merger", "acquisition", "rumor", "squeeze"],
    },
    {
        "label": "Generic business narrative",
        "summary": "Ogolna narracja biznesowa i sektorowa bez wyraznej normatywnej tresci.",
        "descriptor": "demand growth market expansion sector technology services infrastructure opportunity business",
        "keywords": ["demand", "growth", "market", "technology", "services"],
    },
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = URL_RE.sub(" ", lowered)
    lowered = DOMAIN_RE.sub(" ", lowered)
    lowered = CASHTAG_RE.sub(" ", lowered)
    lowered = MENTION_RE.sub(" ", lowered)
    lowered = NON_WORD_RE.sub(" ", lowered)
    lowered = MULTISPACE_RE.sub(" ", lowered).strip()
    return lowered


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text) if token not in TOPIC_DOC_STOPWORDS]


def percentile_scale(values: list[float], target: float) -> float:
    if not values:
        return 50.0
    sorted_values = sorted(values)
    if sorted_values[0] == sorted_values[-1]:
        return 50.0
    less_than = sum(1 for value in sorted_values if value < target)
    equal_to = sum(1 for value in sorted_values if value == target)
    percentile = (less_than + 0.5 * equal_to) / len(sorted_values)
    return max(0.0, min(100.0, 100.0 * percentile))


def topic_keywords(topic: dict, limit: int = 8) -> list[str]:
    keywords: list[str] = []
    for term in topic.get("top_terms", []):
        cleaned = str(term).strip()
        if not cleaned:
            continue
        if cleaned not in keywords:
            keywords.append(cleaned)
        if len(keywords) >= limit:
            break
    return keywords


def term_tokens(term: str) -> list[str]:
    return tokenize(normalize_text(term))


def is_domainish(term: str) -> bool:
    lowered = term.lower().strip()
    if "." in lowered:
        return True
    tokens = term_tokens(lowered)
    return bool(tokens) and all(token in DOMAIN_HINT_TERMS for token in tokens)


def is_generic_term(term: str) -> bool:
    tokens = term_tokens(term)
    if not tokens:
        return True
    return all(token in GENERIC_TOPIC_TERMS or token in DOMAIN_HINT_TERMS for token in tokens)


def is_noise_term(term: str) -> bool:
    lowered = str(term).lower().strip()
    if not lowered:
        return True
    if any(pattern in lowered for pattern in NOISY_TOPIC_PATTERNS):
        return True
    tokens = term_tokens(lowered)
    return bool(tokens) and all(token in NOISY_TOPIC_TERMS or token in DOMAIN_HINT_TERMS for token in tokens)


def prettify_phrase(phrase: str) -> str:
    return " ".join(word.capitalize() for word in phrase.split()[:4])


def build_topic_quality(topic: dict) -> dict:
    keywords = topic_keywords(topic, limit=10)
    keyword_tokens = [token for term in keywords for token in term_tokens(term)]
    unique_keyword_tokens = list(dict.fromkeys(keyword_tokens))
    generic_hits = sum(1 for term in keywords if is_generic_term(term))
    domain_hits = sum(1 for term in keywords if is_domainish(term))
    noise_hits = sum(1 for term in keywords if is_noise_term(term))
    phrase_hits = sum(1 for term in keywords if " " in term)
    example_messages = topic.get("example_messages", [])[:3]
    example_token_lengths = [
        len([token for token in tokenize(str(example.get("snippet") or "")) if token not in GENERIC_TOPIC_TERMS])
        for example in example_messages
    ]
    avg_example_tokens = sum(example_token_lengths) / len(example_token_lengths) if example_token_lengths else 0.0
    example_noise_ratio = (
        sum(
            1
            for example in example_messages
            if any(pattern in str(example.get("snippet") or "").lower() for pattern in NOISY_TOPIC_PATTERNS)
        )
        / max(1, len(example_messages))
    )
    support = min(1.0, math.log1p(int(topic.get("posts_with_topic") or 0)) / math.log1p(3000))
    sentiment_strength = min(1.0, abs(float(topic.get("average_sentiment") or 0.0)) * 2.5)
    generic_ratio = generic_hits / max(1, len(keywords))
    domain_ratio = domain_hits / max(1, len(keywords))
    noise_ratio = noise_hits / max(1, len(keywords))
    specificity = (
        0.38 * (1.0 - generic_ratio)
        + 0.16 * (1.0 - domain_ratio)
        + 0.16 * (1.0 - noise_ratio)
        + 0.20 * min(1.0, avg_example_tokens / 8.0)
        + 0.15 * min(1.0, phrase_hits / max(1, len(keywords)))
    )
    value_relevance = (0.52 * specificity) + (0.30 * support) + (0.18 * sentiment_strength)
    value_relevance -= 0.30 * noise_ratio
    value_relevance -= 0.15 * example_noise_ratio
    value_relevance = max(0.0, min(1.0, value_relevance))

    filtered_keywords = [term for term in keywords if not is_generic_term(term) and not is_noise_term(term)]
    if not filtered_keywords:
        filtered_keywords = [term for term in keywords if not is_generic_term(term)]
    if not filtered_keywords:
        filtered_keywords = keywords[:3]
    display_label = " / ".join(prettify_phrase(term) for term in filtered_keywords[:3]) or f"Topic {topic.get('topic_id')}"

    return {
        "topic_id": int(topic["topic_id"]),
        "keywords": filtered_keywords[:8],
        "display_label": display_label,
        "specificity": round(max(0.0, min(1.0, specificity)), 4),
        "support": round(support, 4),
        "sentiment_strength": round(sentiment_strength, 4),
        "value_relevance": round(value_relevance, 4),
        "generic_ratio": round(generic_ratio, 4),
        "domain_ratio": round(domain_ratio, 4),
        "noise_ratio": round(noise_ratio, 4),
        "unique_keyword_tokens": unique_keyword_tokens,
    }


def select_value_topics(topics: list[dict]) -> tuple[list[dict], list[dict]]:
    enriched_topics: list[dict] = []
    for topic in topics:
        quality = build_topic_quality(topic)
        enriched_topics.append(
            {
                **topic,
                "display_label": quality["display_label"],
                "keywords": quality["keywords"],
                "specificity_score": quality["specificity"],
                "support_score": quality["support"],
                "sentiment_strength": quality["sentiment_strength"],
                "value_relevance": quality["value_relevance"],
                "generic_ratio": quality["generic_ratio"],
                "domain_ratio": quality["domain_ratio"],
                "noise_ratio": quality["noise_ratio"],
                "keyword_tokens": quality["unique_keyword_tokens"],
            }
        )

    enriched_topics.sort(
        key=lambda item: (
            float(item.get("value_relevance") or 0.0),
            float(item.get("corpus_weight") or 0.0),
            int(item.get("posts_with_topic") or 0),
        ),
        reverse=True,
    )

    candidates = [
        topic
        for topic in enriched_topics
        if float(topic.get("specificity_score") or 0.0) >= 0.22
        and float(topic.get("domain_ratio") or 0.0) < 0.55
        and float(topic.get("noise_ratio") or 0.0) < 0.50
        and int(topic.get("posts_with_topic") or 0) >= 25
        and len(list(topic.get("keywords", []))) >= 3
    ]
    target_dimensions = min(len(enriched_topics), max(36, round(len(enriched_topics) * 0.80)))
    if len(candidates) < min(24, target_dimensions):
        candidates = [topic for topic in enriched_topics if float(topic.get("domain_ratio") or 0.0) < 0.75]

    selected = candidates[:target_dimensions]
    if len(selected) < min(len(enriched_topics), 24):
        seen = {int(topic["topic_id"]) for topic in selected}
        for topic in enriched_topics:
            topic_id = int(topic["topic_id"])
            if topic_id in seen:
                continue
            selected.append(topic)
            seen.add(topic_id)
            if len(selected) >= min(len(enriched_topics), 24):
                break

    selected_ids = {int(topic["topic_id"]) for topic in selected}
    discarded = [topic for topic in enriched_topics if int(topic["topic_id"]) not in selected_ids]
    return selected, discarded


def build_value_dimension_catalog(selected_topics: list[dict], family_lookup: dict[int, dict]) -> list[dict]:
    catalog = []
    for topic in selected_topics:
        topic_id = int(topic["topic_id"])
        family = family_lookup.get(topic_id, {})
        examples = [
            str(example.get("snippet") or "").strip()
            for example in topic.get("example_messages", [])[:3]
            if str(example.get("snippet") or "").strip()
        ]
        keywords = list(topic.get("keywords") or topic_keywords(topic))
        catalog.append(
            {
                "axis_id": topic_id,
                "axis_label": str(topic.get("display_label") or topic.get("label_hint") or f"Topic {topic_id}"),
                "axis_display_label": str(topic.get("display_label") or topic.get("label_hint") or f"Topic {topic_id}"),
                "axis_summary": "Organiczny wymiar wartosci odkryty z komentarzy inwestorow. Glowne motywy: " + ", ".join(keywords[:5]) + ".",
                "axis_family_id": family.get("family_id"),
                "axis_family_label": family.get("family_label"),
                "axis_family_summary": family.get("family_summary"),
                "axis_family_dominant_axis_code": family.get("dominant_axis_code"),
                "axis_family_dominant_axis_label": family.get("dominant_axis_label"),
                "family_assignment_score": round(float(family.get("family_assignment_score") or 0.0), 4) if family else 0.0,
                "axis_family_axis_weights": dict(family.get("family_axis_weights") or {}) if family else {},
                "axis_family_base_relevance": round(float(family.get("family_base_relevance") or 0.0), 4) if family else 0.0,
                "axis_family_sort_order": int(family.get("family_sort_order") or 999) if family else 999,
                "keywords": keywords[:8],
                "topic_labels": [str(topic.get("label_hint") or f"Topic {topic_id}")],
                "examples": examples[:3],
                "topic_count": 1,
                "corpus_weight": round(float(topic.get("corpus_weight") or 0.0), 4),
                "average_sentiment": round(float(topic.get("average_sentiment") or 0.0), 4),
                "value_relevance": round(float(topic.get("value_relevance") or 0.0), 4),
                "specificity_score": round(float(topic.get("specificity_score") or 0.0), 4),
            }
        )
    return sorted(catalog, key=lambda item: int(item["axis_id"]))


def build_family_catalog(
    dimension_catalog: list[dict],
    selected_topics: list[dict],
) -> list[dict]:
    if not dimension_catalog:
        return []

    topic_lookup = {int(topic["topic_id"]): topic for topic in selected_topics}
    family_buckets: dict[str, list[dict]] = defaultdict(list)
    for dimension in dimension_catalog:
        family_id = str(dimension.get("axis_family_id") or "").strip()
        if not family_id:
            continue
        family_buckets[family_id].append(dimension)

    family_rows: list[dict] = []
    for family_id, dimensions in family_buckets.items():
        sorted_dimensions = sorted(
            dimensions,
            key=lambda item: (
                float(item.get("value_relevance") or 0.0),
                float(item.get("corpus_weight") or 0.0),
            ),
            reverse=True,
        )
        family_label = str(sorted_dimensions[0].get("axis_family_label") or sorted_dimensions[0].get("axis_label") or family_id)

        keywords: list[str] = []
        examples: list[str] = []
        topic_labels: list[str] = []
        member_axis_ids: list[int] = []
        weighted_relevance_sum = 0.0
        weighted_assignment_sum = 0.0
        weight_sum = 0.0
        family_summary = str(sorted_dimensions[0].get("axis_family_summary") or sorted_dimensions[0].get("axis_summary") or "")
        family_assignment_scores: list[float] = []
        family_sort_order = 999
        family_axis_weights = {}
        family_base_relevance = 0.0

        for dimension in sorted_dimensions:
            axis_id = int(dimension["axis_id"])
            member_axis_ids.append(axis_id)
            topic = topic_lookup.get(axis_id, {})
            dimension_weight = max(
                0.20,
                float(dimension.get("value_relevance") or 0.0)
                + min(1.0, float(dimension.get("corpus_weight") or 0.0) / 2000.0),
            )
            weighted_relevance_sum += float(dimension.get("value_relevance") or 0.0) * dimension_weight
            weighted_assignment_sum += float(dimension.get("family_assignment_score") or 0.0) * dimension_weight
            weight_sum += dimension_weight
            family_assignment_scores.append(float(dimension.get("family_assignment_score") or 0.0))

            for keyword in list(dimension.get("keywords") or [])[:6]:
                if keyword and keyword not in keywords:
                    keywords.append(str(keyword))
                if len(keywords) >= 10:
                    break

            for topic_label in list(dimension.get("topic_labels") or [])[:2]:
                if topic_label and topic_label not in topic_labels:
                    topic_labels.append(str(topic_label))
                if len(topic_labels) >= 8:
                    break

            source_examples = list(dimension.get("examples") or topic.get("example_messages") or [])
            for example in source_examples[:3]:
                snippet = str(example.get("snippet") if isinstance(example, dict) else example).strip()
                if snippet and snippet not in examples:
                    examples.append(snippet)
                if len(examples) >= 4:
                    break

            family_axis_weights = family_axis_weights or dict((dimension.get("axis_family_axis_weights") or {}))
            family_base_relevance = max(family_base_relevance, float(dimension.get("axis_family_base_relevance") or 0.0))
            family_sort_order = min(family_sort_order, int(dimension.get("axis_family_sort_order") or 999))

        family_rows.append(
            {
                "family_id": family_id,
                "family_label": family_label,
                "family_summary": family_summary or f"Komentarzowa rodzina ESG-like. Najczestsze motywy: {', '.join(keywords[:5])}.",
                "keywords": keywords[:10],
                "examples": examples[:4],
                "topic_labels": topic_labels[:8],
                "member_axis_ids": member_axis_ids,
                "member_dimensions_count": len(member_axis_ids),
                "average_value_relevance": round((weighted_relevance_sum / weight_sum) if weight_sum > 0 else 0.0, 4),
                "average_assignment_score": round((weighted_assignment_sum / weight_sum) if weight_sum > 0 else 0.0, 4),
                "family_sort_order": family_sort_order,
                "family_base_relevance": round(family_base_relevance, 4),
            }
        )

    catalog: list[dict] = []
    for row in family_rows:
        catalog.append(
            {
                "family_id": row["family_id"],
                "family_label": row["family_label"],
                "family_summary": row["family_summary"],
                "keywords": row["keywords"],
                "examples": row["examples"],
                "topic_labels": row["topic_labels"],
                "member_axis_ids": row["member_axis_ids"],
                "member_dimensions_count": row["member_dimensions_count"],
                "average_value_relevance": row["average_value_relevance"],
                "average_assignment_score": row["average_assignment_score"],
                "sort_order": row["family_sort_order"],
            }
        )

    catalog.sort(
        key=lambda item: (
            int(item.get("sort_order") or 999),
            -float(item.get("average_value_relevance") or 0.0),
            -int(item.get("member_dimensions_count") or 0),
        ),
    )
    return catalog


def build_dimension_scores(company_rows: list[dict], dimension_catalog: list[dict]) -> tuple[dict[str, list[dict]], dict[int, list[float]]]:
    raw_values_by_dimension: dict[int, list[float]] = defaultdict(list)
    company_dimensions: dict[str, list[dict]] = {}
    catalog_by_id = {int(item["axis_id"]): item for item in dimension_catalog}

    for row in company_rows:
        symbol = str(row.get("symbol") or "").upper()
        payload: list[dict] = []
        for topic_payload in list(row.get("topics", [])):
            topic_id = int(topic_payload.get("topic_id", -1))
            if topic_id not in catalog_by_id:
                continue
            axis_definition = catalog_by_id[topic_id]
            raw_score = float(topic_payload.get("signed_topic_score") or 0.0)
            raw_values_by_dimension[topic_id].append(raw_score)
            payload.append(
                {
                    "axis_id": topic_id,
                    "axis_label": axis_definition["axis_label"],
                    "axis_summary": axis_definition["axis_summary"],
                    "axis_family_id": axis_definition.get("axis_family_id"),
                    "axis_family_label": axis_definition.get("axis_family_label"),
                    "axis_keywords": axis_definition["keywords"],
                    "axis_examples": axis_definition["examples"][:2],
                    "axis_raw_score": raw_score,
                    "axis_exposure": float(topic_payload.get("topic_share") or 0.0),
                    "axis_posts_count": int(topic_payload.get("posts_with_topic") or 0),
                    "axis_avg_sentiment": float(topic_payload.get("avg_sentiment") or 0.0),
                }
            )
        company_dimensions[symbol] = payload

    for symbol, payload in company_dimensions.items():
        normalized_payload = []
        for item in payload:
            axis_id = int(item["axis_id"])
            percentile = percentile_scale(raw_values_by_dimension[axis_id], item["axis_raw_score"])
            exposure = float(item["axis_exposure"] or 0.0)
            posts_count = int(item["axis_posts_count"] or 0)
            confidence = min(1.0, math.log1p(posts_count) / math.log1p(15)) * min(1.0, 0.20 + (0.80 * min(1.0, exposure * 3.5)))
            axis_score = 50.0 + confidence * (percentile - 50.0)
            normalized_payload.append(
                {
                    "axis_id": axis_id,
                    "axis_label": item["axis_label"],
                    "axis_summary": item["axis_summary"],
                    "axis_family_id": item["axis_family_id"],
                    "axis_family_label": item["axis_family_label"],
                    "axis_score": round(axis_score, 2),
                    "axis_raw_score": round(item["axis_raw_score"], 4),
                    "axis_exposure": round(exposure, 4),
                    "axis_confidence": round(confidence, 4),
                    "axis_posts_count": posts_count,
                    "axis_keywords": item["axis_keywords"],
                    "axis_examples": item["axis_examples"],
                    "axis_avg_sentiment": round(item["axis_avg_sentiment"], 4),
                }
            )
        normalized_payload.sort(key=lambda item: item["axis_exposure"], reverse=True)
        company_dimensions[symbol] = normalized_payload

    return company_dimensions, raw_values_by_dimension


def build_family_scores(
    company_dimensions: dict[str, list[dict]],
    family_catalog: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, list[float]]]:
    family_catalog_by_id = {str(item["family_id"]): item for item in family_catalog}
    raw_values_by_family: dict[str, list[float]] = defaultdict(list)
    company_families: dict[str, list[dict]] = {}

    for symbol, dimensions in company_dimensions.items():
        family_buckets: dict[str, dict] = {}
        for dimension in dimensions:
            family_id = str(dimension.get("axis_family_id") or f"value-family-axis-{dimension['axis_id']}")
            family_definition = family_catalog_by_id.get(family_id)
            if family_definition is None:
                continue

            bucket = family_buckets.setdefault(
                family_id,
                {
                    "family_id": family_id,
                    "family_label": family_definition["family_label"],
                    "family_summary": family_definition["family_summary"],
                    "family_keywords": family_definition["keywords"],
                    "family_examples": family_definition["examples"],
                    "weighted_raw_sum": 0.0,
                    "signal_weight_sum": 0.0,
                    "family_exposure": 0.0,
                    "family_posts_count": 0,
                    "member_dimensions": [],
                },
            )

            exposure = float(dimension.get("axis_exposure") or 0.0)
            confidence = float(dimension.get("axis_confidence") or 0.0)
            signal_weight = max(0.03, exposure) * (0.25 + (0.75 * confidence))
            raw_score = float(dimension.get("axis_raw_score") or 0.0)
            bucket["weighted_raw_sum"] += raw_score * signal_weight
            bucket["signal_weight_sum"] += signal_weight
            bucket["family_exposure"] += exposure
            bucket["family_posts_count"] += int(dimension.get("axis_posts_count") or 0)
            bucket["member_dimensions"].append(
                {
                    "axis_id": int(dimension["axis_id"]),
                    "axis_label": str(dimension["axis_label"]),
                    "axis_score": float(dimension["axis_score"]),
                    "axis_raw_score": raw_score,
                    "axis_exposure": exposure,
                    "axis_confidence": confidence,
                }
            )

        family_payload: list[dict] = []
        for family_id, bucket in family_buckets.items():
            signal_weight_sum = float(bucket["signal_weight_sum"])
            family_raw_score = (float(bucket["weighted_raw_sum"]) / signal_weight_sum) if signal_weight_sum > 0 else 0.0
            raw_values_by_family[family_id].append(family_raw_score)
            family_payload.append(
                {
                    "family_id": family_id,
                    "family_label": bucket["family_label"],
                    "family_summary": bucket["family_summary"],
                    "family_keywords": bucket["family_keywords"],
                    "family_examples": bucket["family_examples"],
                    "family_raw_score": family_raw_score,
                    "family_exposure": min(1.0, float(bucket["family_exposure"])),
                    "family_posts_count": int(bucket["family_posts_count"]),
                    "family_dimension_count": len(bucket["member_dimensions"]),
                    "family_member_dimensions": sorted(
                        bucket["member_dimensions"],
                        key=lambda item: (item["axis_exposure"], abs(item["axis_raw_score"])),
                        reverse=True,
                    )[:8],
                }
            )
        company_families[symbol] = family_payload

    for symbol, family_payload in company_families.items():
        normalized_payload = []
        for item in family_payload:
            percentile = percentile_scale(raw_values_by_family[item["family_id"]], float(item["family_raw_score"]))
            evidence_units = int(item["family_dimension_count"]) + min(int(item["family_posts_count"]), 24)
            exposure = float(item["family_exposure"])
            confidence = min(1.0, math.log1p(evidence_units) / math.log1p(28)) * min(
                1.0,
                0.20 + (0.80 * min(1.0, exposure * 1.8)),
            )
            family_score = 50.0 + confidence * (percentile - 50.0)
            normalized_payload.append(
                {
                    "family_id": item["family_id"],
                    "family_label": item["family_label"],
                    "family_summary": item["family_summary"],
                    "family_score": round(family_score, 2),
                    "family_raw_score": round(float(item["family_raw_score"]), 4),
                    "family_exposure": round(exposure, 4),
                    "family_confidence": round(confidence, 4),
                    "family_posts_count": int(item["family_posts_count"]),
                    "family_dimension_count": int(item["family_dimension_count"]),
                    "family_keywords": item["family_keywords"],
                    "family_examples": item["family_examples"][:3],
                    "family_member_dimensions": item["family_member_dimensions"],
                }
            )
        normalized_payload.sort(
            key=lambda item: (
                float(item.get("family_exposure") or 0.0),
                float(item.get("family_confidence") or 0.0),
            ),
            reverse=True,
        )
        company_families[symbol] = normalized_payload

    return company_families, raw_values_by_family


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-file", type=str, default=None)
    parser.add_argument("--company-topics-file", type=str, default=None)
    parser.add_argument("--topic-summary-file", type=str, default=None)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    posts_path = Path(args.posts_file) if args.posts_file else (POSTS_SCORED_SAMPLE_PATH if args.sample else POSTS_SCORED_PATH)
    company_topics_path = Path(args.company_topics_file) if args.company_topics_file else (
        COMPANY_TOPIC_FEATURES_SAMPLE_PATH if args.sample else COMPANY_TOPIC_FEATURES_PATH
    )
    topic_summary_path = Path(args.topic_summary_file) if args.topic_summary_file else (
        TOPIC_SUMMARY_SAMPLE_PATH if args.sample else TOPIC_SUMMARY_PATH
    )
    output_path = COMMENT_ESG_FEATURES_SAMPLE_PATH if args.sample else COMMENT_ESG_FEATURES_PATH
    summary_path = COMMENT_ESG_SUMMARY_SAMPLE_PATH if args.sample else COMMENT_ESG_SUMMARY_PATH

    if not posts_path.exists():
        raise FileNotFoundError(f"Brak pliku z postami: {posts_path}")
    if not company_topics_path.exists():
        raise FileNotFoundError(f"Brak pliku z cechami topicznymi spolek: {company_topics_path}")
    if not topic_summary_path.exists():
        raise FileNotFoundError(f"Brak podsumowania topicow: {topic_summary_path}")

    posts_rows = load_jsonl(posts_path)
    company_rows = load_jsonl(company_topics_path)
    topic_summary = load_json(topic_summary_path)
    topics = list(topic_summary.get("topics", []))

    if len(company_rows) < 25 or len(topics) < 10:
        raise RuntimeError("Za malo danych do zbudowania wymiarow wartosci z komentarzy.")

    selected_topics, discarded_topics = select_value_topics(topics)
    dimension_catalog = build_value_dimension_catalog(selected_topics, {})
    family_catalog = build_family_catalog(dimension_catalog, selected_topics)
    company_dimensions, _raw_values_by_dimension = build_dimension_scores(company_rows, dimension_catalog)
    company_families, _raw_values_by_family = build_family_scores(company_dimensions, family_catalog)

    output_rows = []
    with output_path.open("w", encoding="utf-8") as handle:
        for row in sorted(company_rows, key=lambda item: str(item.get("symbol") or "")):
            symbol = str(row.get("symbol") or "").upper()
            dimensions = company_dimensions.get(symbol, [])
            output_row = {
                "symbol": symbol,
                "company_name": row.get("company_name") or symbol,
                "category": row.get("category") or "Unknown",
                "posts_count": row.get("posts_count", 0),
                "custom_esg_axes": dimensions,
                "custom_esg_families": company_families.get(symbol, []),
            }
            handle.write(json.dumps(output_row, ensure_ascii=False) + "\n")
            output_rows.append(output_row)

    summary = {
        "input_posts_file": str(posts_path),
        "input_company_topics_file": str(company_topics_path),
        "input_topic_summary_file": str(topic_summary_path),
        "output_company_esg_file": str(output_path),
        "companies_scored": len(output_rows),
        "raw_topics_count": len(topics),
        "dimensions_count": len(dimension_catalog),
        "families": family_catalog,
        "family_count": len(family_catalog),
        "axes": dimension_catalog,
        "discarded_topics_count": len(discarded_topics),
        "discarded_topics_preview": [
            {
                "topic_id": int(item["topic_id"]),
                "label": str(item.get("display_label") or item.get("label_hint") or f"Topic {item['topic_id']}"),
                "keywords": list(item.get("keywords", []))[:6],
                "value_relevance": round(float(item.get("value_relevance") or 0.0), 4),
                "specificity_score": round(float(item.get("specificity_score") or 0.0), 4),
                "domain_ratio": round(float(item.get("domain_ratio") or 0.0), 4),
            }
            for item in discarded_topics[:12]
        ],
        "projection_method": "organic-topic-dimensions",
        "is_sample": args.sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
