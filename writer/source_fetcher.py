"""
Lightweight source discovery and extraction for CapCut article drafting.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}

OFFICIAL_DOMAIN_HINTS = (
    "capcut.com",
    "play.google.com",
    "apps.apple.com",
)

LOW_VALUE_SOURCE_HINTS = (
    "privacy",
    "terms",
    "cookie",
)


def discover_source_urls(opportunity: dict) -> list[str]:
    query = (opportunity.get("query") or "").lower()
    bucket = (opportunity.get("bucket") or "").lower()
    scored: list[tuple[int, str]] = []

    for url in config.OFFICIAL_SOURCE_URLS:
        score = _score_source_url(url, query, bucket)
        if score > 0:
            scored.append((score, url))

    scored.sort(key=lambda item: (-item[0], item[1]))
    unique = []
    seen = set()
    for _, url in scored:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
        if len(unique) >= config.ARTICLE_MAX_SOURCES:
            break
    return unique


def fetch_multiple_sources(urls: list[str], max_sources: int = 5) -> list[dict]:
    sources: list[dict] = []
    for url in (urls or [])[:max_sources]:
        extracted = fetch_article_text(url)
        if extracted:
            sources.append(extracted)
    return sources


def fetch_article_text(url: str, max_chars: int = 2200) -> dict | None:
    if not url:
        return None
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        logger.debug("Source fetch failed for %s: %s", url, exc)
        return None

    html = response.text or ""
    if not html.strip():
        return None

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _clean_text(title_match.group(1) if title_match else "")

    clean = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<style[^>]*>.*?</style>", " ", clean, flags=re.IGNORECASE | re.DOTALL)
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", clean, flags=re.IGNORECASE | re.DOTALL)
    text_parts = []
    for part in paragraphs:
        text = _clean_text(part)
        if len(text) >= 50:
            text_parts.append(text)
    text = "\n\n".join(text_parts)
    if len(text) < 180:
        body_text = _clean_text(re.sub(r"<[^>]+>", " ", clean))
        text = body_text[:max_chars]

    if len(text) < 180:
        return None

    domain = urlparse(url).netloc.lower().lstrip("www.")
    return {
        "title": title,
        "text": text[:max_chars],
        "source_domain": domain,
        "url": url,
        "is_official": _is_official_domain(domain),
    }


def summarize_source_quality(source_texts: list[dict]) -> dict:
    source_domains: list[str] = []
    source_urls: list[str] = []
    official_domains: set[str] = set()

    for source in source_texts or []:
        domain = (source.get("source_domain") or "").strip().lower()
        url = (source.get("url") or "").strip()
        if domain:
            source_domains.append(domain)
            if _is_official_domain(domain):
                official_domains.add(domain)
        if url:
            source_urls.append(url)

    unique_domains = sorted(set(source_domains))
    quality = {
        "source_count": len(source_texts or []),
        "source_domains": unique_domains,
        "unique_domain_count": len(unique_domains),
        "official_count": len(official_domains),
        "source_urls": source_urls,
        "flags": [],
    }
    if quality["source_count"] < config.ARTICLE_MIN_SOURCE_COUNT:
        quality["flags"].append(
            f"Only {quality['source_count']} source(s) were extracted; target is {config.ARTICLE_MIN_SOURCE_COUNT}+."
        )
    if quality["unique_domain_count"] < config.ARTICLE_MIN_UNIQUE_SOURCE_DOMAINS:
        quality["flags"].append(
            "Source diversity is weak; article may repeat one source's framing."
        )
    if quality["official_count"] < 1:
        quality["flags"].append("No official CapCut or app-store source was captured.")
    quality["needs_manual_fact_check"] = bool(quality["flags"])
    return quality


def _score_source_url(url: str, query: str, bucket: str) -> int:
    normalized_url = (url or "").lower()
    score = 1
    for hint in LOW_VALUE_SOURCE_HINTS:
        if hint in normalized_url:
            score -= 2
    if _is_official_domain(urlparse(url).netloc.lower()):
        score += 4

    tokens = _keyword_tokens(query)
    for token in tokens:
        if token and token in normalized_url:
            score += 3

    bucket_hints = {
        "tutorial": ("editor", "tool"),
        "how_to": ("editor", "tool"),
        "fix": ("play.google.com", "apps.apple.com", "editor"),
        "platform": ("editor", "play.google.com", "apps.apple.com"),
        "update": ("play.google.com", "apps.apple.com"),
        "safety": ("play.google.com", "apps.apple.com"),
        "download": ("play.google.com", "apps.apple.com"),
        "trend": ("editor", "tool"),
    }
    for hint in bucket_hints.get(bucket, ()):
        if hint in normalized_url:
            score += 2
    return score


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _keyword_tokens(query: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", query or "") if len(token) > 2}


def _is_official_domain(domain: str) -> bool:
    return any(hint in (domain or "") for hint in OFFICIAL_DOMAIN_HINTS)
