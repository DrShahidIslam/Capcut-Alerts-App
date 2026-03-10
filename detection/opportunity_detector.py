"""
Convert mixed source signals into ranked article opportunities.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict

import config


NON_COMPARISON_BUCKETS = {"how_to", "fix", "trend", "safety", "download"}


def detect_opportunities(existing_slugs: set[str], source_bundles: list[list[dict]]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for bundle in source_bundles:
        for item in bundle:
            query = _normalize_query(item.get("query", ""))
            if not query:
                continue
            grouped[_topic_key(query)].append({**item, "query": query})

    opportunities = []
    for topic_key, items in grouped.items():
        canonical_query = items[0]["query"]
        slug = _slugify(canonical_query)
        if slug in existing_slugs or slug in config.EXCLUDE_SLUG_HINTS:
            continue
        bucket = _classify(canonical_query)
        score = _score_topic(canonical_query, items, bucket)
        if score < config.MIN_OPPORTUNITY_SCORE:
            continue
        opportunities.append(
            {
                "topic_key": topic_key,
                "query": canonical_query,
                "slug": slug,
                "score": score,
                "bucket": bucket,
                "source_count": len({item["source"] for item in items}),
                "sources": sorted({item["source"] for item in items}),
                "signals": sorted({signal for item in items for signal in item.get("signals", [])}),
                "freshness": round(sum(item.get("freshness", 0.5) for item in items) / len(items), 2),
                "volume": _aggregate_volume(items),
                "title": suggest_title(canonical_query, bucket),
                "brief": build_brief(canonical_query, bucket, items),
                "status": "new",
            }
        )

    return _select_diverse_opportunities(opportunities)


def suggest_title(query: str, bucket: str) -> str:
    clean = query.strip()
    if bucket == "comparison":
        return clean.title().replace(" Vs ", " vs ") + ": Which Editor Is Better?"
    if bucket == "fix":
        return clean.title() + ": Causes and Working Fixes"
    if bucket == "trend":
        return clean.title() + ": What Is Trending Right Now?"
    if bucket == "safety":
        return clean.title() + ": Is It Safe, Legal, and Worth It?"
    if bucket == "download":
        return clean.title() + ": Full Download and Setup Guide"
    return clean.title() + ": Complete Guide"


def build_brief(query: str, bucket: str, items: list[dict]) -> str:
    competitor = any("competitor-covered" in item.get("signals", []) for item in items)
    trend = any("rising" in item.get("signals", []) or "fresh-news" in item.get("signals", []) for item in items)
    momentum = any("momentum" in item.get("signals", []) for item in items)
    volume = _aggregate_volume(items)
    parts = [f"Primary angle: {bucket.replace('_', ' ')}."]
    if competitor:
        parts.append("Competitors are already covering related demand.")
    if trend:
        parts.append("Include a timely update section for current search intent.")
    if momentum:
        parts.append("Recent trend momentum detected; highlight what's driving interest.")
    if volume:
        parts.append(f"Search volume signal detected (score: {volume}).")
    parts.append("Answer search intent fast, compare alternatives honestly, and add internal links to existing CapCut posts.")
    return " ".join(parts)


def _aggregate_volume(items: list[dict]) -> int:
    volumes = [int(item.get("volume", 0)) for item in items if str(item.get("volume", "")).isdigit()]
    if not volumes:
        return 0
    return int(sum(volumes) / len(volumes))


def _score_topic(query: str, items: list[dict], bucket: str) -> int:
    base = 22
    source_weight = len({item["source"] for item in items}) * 8
    freshness = int(sum(item.get("freshness", 0.5) for item in items) / len(items) * 22)
    keyword_bonus = 0
    lower = query.lower()
    for term in config.KEYWORD_EXPANSION_TERMS:
        if term in lower:
            keyword_bonus += 3

    volume_signal = _aggregate_volume(items)
    volume_bonus = 0
    if volume_signal >= 60:
        volume_bonus = 12
    elif volume_signal >= 30:
        volume_bonus = 8
    elif volume_signal >= 10:
        volume_bonus = 4

    momentum_bonus = 6 if any("momentum" in item.get("signals", []) for item in items) else 0

    strategic = config.STRATEGIC_BUCKET_BOOSTS.get(bucket, 6)
    return min(base + source_weight + freshness + keyword_bonus + volume_bonus + momentum_bonus + strategic, 100)


def _select_diverse_opportunities(opportunities: list[dict]) -> list[dict]:
    if not opportunities:
        return []

    limit = config.MAX_OPPORTUNITIES_PER_RUN
    comparison_cap = max(1, math.ceil(limit * config.MAX_COMPARISON_SHARE))
    bucket_cap = max(2, math.ceil(limit * config.MAX_BUCKET_SHARE))

    pool = sorted(opportunities, key=lambda item: (-item["score"], item["query"]))
    bucket_counts: Counter[str] = Counter()
    selected: list[dict] = []

    # Ensure at least one from each non-comparison bucket when available.
    for bucket in NON_COMPARISON_BUCKETS:
        bucket_items = [item for item in pool if item["bucket"] == bucket]
        if not bucket_items:
            continue
        picked = bucket_items[0]
        if picked in selected:
            continue
        selected.append(picked)
        bucket_counts[bucket] += 1

    remaining = [item for item in pool if item not in selected]

    while remaining and len(selected) < limit:
        ranked = sorted(
            remaining,
            key=lambda item: (
                -(item["score"] - bucket_counts[item["bucket"]] * config.DIVERSITY_PENALTY_PER_BUCKET),
                bucket_counts[item["bucket"]],
                item["query"],
            ),
        )
        picked = None
        for item in ranked:
            bucket = item["bucket"]
            max_for_bucket = comparison_cap if bucket == "comparison" else bucket_cap
            if bucket_counts[bucket] >= max_for_bucket:
                continue
            picked = item
            break
        if picked is None:
            break
        selected.append(picked)
        bucket_counts[picked["bucket"]] += 1
        remaining = [item for item in remaining if item["topic_key"] != picked["topic_key"]]

    return selected


def _classify(query: str) -> str:
    lower = query.lower()
    if "vs " in lower or "compare" in lower:
        return "comparison"
    if any(token in lower for token in ("fix", "error", "issue", "problem", "not working", "black screen", "login")):
        return "fix"
    if any(token in lower for token in ("trend", "trending", "viral", "template")):
        return "trend"
    if any(token in lower for token in ("safe", "legal", "privacy", "ban")):
        return "safety"
    if any(token in lower for token in ("download", "apk", "install", "pc", "ios", "android", "old version")):
        return "download"
    return "how_to"


def _normalize_query(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    value = value.replace("|", " ").replace(":", " ")
    value = re.sub(r"[^a-zA-Z0-9+/\- ]", "", value).strip()
    return value.lower()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _topic_key(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()
