"""
Convert mixed source signals into ranked article opportunities.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict

import config


NON_COMPARISON_BUCKETS = {
    "how_to", "fix", "trend", "safety", "download",
    "tutorial", "alternative", "platform", "update",
}


def detect_opportunities(existing_slugs: set[str], source_bundles: list[list[dict]]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for bundle in source_bundles:
        for item in bundle:
            query = _normalize_query(item.get("query", ""))
            if not query:
                continue
            if _is_low_value_query(query):
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
        return clean.title().replace(" Vs ", " vs ") + " (2026): Honest Feature Comparison [With Table]"
    if bucket == "fix":
        return clean.title() + ": 5 Working Fixes That Actually Work [2026]"
    if bucket == "trend":
        return clean.title() + ": Trending Now + How to Use It [2026]"
    if bucket == "safety":
        return clean.title() + ": Safety, Risks, and What You Need to Know [2026]"
    if bucket == "download":
        return clean.title() + ": Safe Download + Install Guide [Latest Version]"
    if bucket == "tutorial":
        return "How to " + clean.title() + ": Step by Step Tutorial for Beginners [2026]"
    if bucket == "alternative":
        return "Best " + clean.title() + " Alternatives in 2026 [Free and Paid]"
    if bucket == "platform":
        return clean.title() + ": Complete Guide for Every Platform [2026]"
    if bucket == "update":
        return clean.title() + ": What's New and How to Update [2026]"
    return "How to " + clean.title() + " in CapCut [Step by Step Guide 2026]"


def build_brief(query: str, bucket: str, items: list[dict]) -> str:
    competitor = any("competitor-covered" in item.get("signals", []) for item in items)
    trend = any("rising" in item.get("signals", []) or "fresh-news" in item.get("signals", []) for item in items)
    momentum = any("momentum" in item.get("signals", []) for item in items)
    volume = _aggregate_volume(items)

    # Bucket-specific angle descriptions
    bucket_angles = {
        "comparison": "Head-to-head feature comparison with decision table.",
        "how_to": "Step-by-step guide with practical walkthrough.",
        "fix": "Troubleshooting guide with causes and verified fixes.",
        "trend": "Trend analysis with recreation steps.",
        "safety": "Safety and legality analysis with risk factors.",
        "download": "Safe download and setup walkthrough.",
        "tutorial": "Beginner-friendly tutorial with numbered steps and common mistakes.",
        "alternative": "Alternatives roundup with feature comparison table and best-for recommendations.",
        "platform": "Platform-specific guide with system requirements and compatibility notes.",
        "update": "Update changelog with what's new, how to update, and before/after changes.",
    }
    angle = bucket_angles.get(bucket, f"Primary angle: {bucket.replace('_', ' ')}.")
    parts = [angle]

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
    credibility_penalty = 0
    signals = {signal for item in items for signal in item.get("signals", [])}
    if bucket == "trend" and not {"rising", "momentum", "fresh-news", "competitor-covered"} & signals:
        credibility_penalty += 18
    if bucket == "download" and any(token in lower for token in ("mod apk", "mod", "apk")):
        credibility_penalty += 8

    strategic = config.STRATEGIC_BUCKET_BOOSTS.get(bucket, 6)
    return min(base + source_weight + freshness + keyword_bonus + volume_bonus + momentum_bonus + strategic - credibility_penalty, 100)


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
    # Comparison: must check first since "vs" is unambiguous
    if "vs " in lower or "compare" in lower:
        return "comparison"
    # Fix/troubleshoot
    if any(token in lower for token in ("fix", "error", "issue", "problem", "not working", "black screen", "login", "crashing", "freezing", "sync problem", "failed")):
        return "fix"
    # Tutorial: explicit step-by-step how-to queries
    if re.search(r"\bhow to\b", lower) and any(token in lower for token in ("step", "tutorial", "beginner", "guide")):
        return "tutorial"
    if re.search(r"\bhow to\b", lower):
        return "tutorial"
    # Alternative: "alternative", "apps like", "editors like"
    if any(token in lower for token in ("alternative", "apps like", "editors like", "similar to")):
        return "alternative"
    # Update / changelog
    if any(token in lower for token in ("update", "changelog", "new version", "new features", "what's new", "whats new", "new effects")):
        return "update"
    # Platform-specific
    if any(token in lower for token in ("for pc", "for ios", "for mac", "for chromebook", "web version", "online editor", "for android")) and "download" not in lower and "apk" not in lower:
        return "platform"
    # Trends
    if any(token in lower for token in ("trend", "trending", "viral", "template")):
        return "trend"
    # Safety
    if any(token in lower for token in ("safe", "legal", "privacy", "ban", "risk")):
        return "safety"
    # Download
    if any(token in lower for token in ("download", "apk", "install", "old version", "mod", "lite version")):
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


def _is_low_value_query(query: str) -> bool:
    lower = query.lower().strip()
    generic_patterns = (
        "capcut trending templates",
        "capcut template trend",
        "capcut new effects",
        "capcut latest version changelog",
    )
    if lower in generic_patterns:
        return True
    if "template" in lower and ("2026" in lower or "trend" in lower) and len(lower.split()) <= 4:
        return True
    if lower.startswith("best capcut alternatives"):
        return True
    return False

