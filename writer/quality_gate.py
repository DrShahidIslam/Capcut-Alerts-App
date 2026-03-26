"""
Editorial quality checks for CapCut drafts before publish.
"""
from __future__ import annotations

import re

import config

GENERIC_TREND_PATTERNS = (
    r"why this trend works",
    r"boost your views",
    r"taken over tiktok",
    r"viral format",
)


def validate_article_for_publish(article: dict, min_words: int | None = None) -> dict:
    article = article or {}
    min_words = min_words or config.PUBLISH_MIN_WORDS
    issues: list[str] = []
    warnings: list[str] = []

    content = article.get("content") or ""
    text = re.sub(r"<[^>]+>", " ", content)
    text = re.sub(r"\s+", " ", text).strip()
    words = [word for word in text.split(" ") if word]

    bucket = (article.get("bucket") or "").lower()
    source_quality = article.get("source_quality") or {}
    source_count = int(source_quality.get("source_count") or 0)
    unique_domains = int(source_quality.get("unique_domain_count") or 0)
    official_count = int(source_quality.get("official_count") or 0)
    editorial_flags = article.get("editorial_flags") or []
    link_count = len(re.findall(r'<a\s+[^>]*href="https://capcutpro-apks\.com/', content, flags=re.IGNORECASE))
    h2_count = len(re.findall(r"<h2\b", content, flags=re.IGNORECASE))

    if len(words) < min_words:
        issues.append(f"Draft is too thin at {len(words)} words; minimum is {min_words}.")
    if link_count < 2:
        issues.append("Internal linking is weak; draft needs at least 2 real internal links.")
    if h2_count < 4:
        warnings.append("Structure is light; add more focused H2 sections.")
    if not article.get("meta_title"):
        issues.append("Meta title is missing.")
    if not article.get("meta_description"):
        issues.append("Meta description is missing.")
    if article.get("faq_count", 0) < 3:
        warnings.append("FAQ coverage is thin for a review draft.")

    if article.get("is_fallback"):
        if bucket in {"trend", "update", "download", "safety"}:
            issues.append(f"{bucket.title()} draft is template fallback only and should not be published.")
        else:
            warnings.append("Draft used the template fallback instead of model output.")

    if bucket in {"trend", "update"} and source_count < 2:
        issues.append(f"{bucket.title()} drafts require at least 2 sources.")
    if bucket in {"download", "safety", "platform"} and official_count < 1:
        issues.append(f"{bucket.title()} drafts require at least 1 official source.")
    if source_count < config.ARTICLE_MIN_SOURCE_COUNT:
        warnings.append("Source coverage is thin.")
    if unique_domains < config.ARTICLE_MIN_UNIQUE_SOURCE_DOMAINS:
        warnings.append("Source diversity is weak.")
    if article.get("needs_manual_fact_check"):
        warnings.append("Draft still needs manual fact-checking.")
    if editorial_flags:
        warnings.extend(str(flag) for flag in editorial_flags)

    if bucket == "trend":
        lowered = text.lower()
        if any(re.search(pattern, lowered) for pattern in GENERIC_TREND_PATTERNS):
            issues.append("Trend draft reads like generic filler instead of evidence-backed guidance.")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": _dedupe_keep_order(warnings),
        "word_count": len(words),
        "internal_links": link_count,
        "source_count": source_count,
        "unique_domain_count": unique_domains,
        "official_count": official_count,
    }


def _dedupe_keep_order(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
