"""
Competitor sitemap and RSS topic extraction.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse
from xml.etree import ElementTree

import feedparser
import requests

import config

logger = logging.getLogger(__name__)


def fetch_competitor_topics() -> list[dict]:
    topics = []
    for sitemap_url in config.COMPETITOR_SITEMAPS:
        topics.extend(_fetch_topics_from_sitemap(sitemap_url))
    for feed_url in config.RSS_FEEDS:
        topics.extend(_fetch_topics_from_feed(feed_url))
    return topics


def _fetch_topics_from_sitemap(sitemap_url: str) -> list[dict]:
    topics = []
    try:
        response = requests.get(sitemap_url, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            return []
        root = ElementTree.fromstring(response.text)
        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}")[0] + "}"
        for loc in root.findall(f".//{namespace}loc"):
            url = (loc.text or "").strip()
            if not _is_relevant_url(url):
                continue
            slug = urlparse(url).path.strip("/").replace("-", " ")
            if slug:
                topics.append(
                    {
                        "query": slug,
                        "source": "competitor_sitemap",
                        "signals": ["competitor-covered"],
                        "freshness": 0.65,
                        "volume": 0,
                    }
                )
    except Exception as exc:
        logger.debug("Competitor sitemap failed for %s: %s", sitemap_url, exc)
    return topics


def _fetch_topics_from_feed(feed_url: str) -> list[dict]:
    topics = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:12]:
            title = re.sub(r"\s+", " ", getattr(entry, "title", "")).strip()
            if not title:
                continue
            if not _is_relevant_title(title):
                continue
            topics.append(
                {
                    "query": title,
                    "source": "news_feed",
                    "signals": ["fresh-news"],
                    "freshness": 0.9,
                    "volume": 0,
                }
            )
    except Exception as exc:
        logger.debug("Feed parse failed for %s: %s", feed_url, exc)
    return topics


def _is_relevant_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    if "capcut" in lower:
        return True
    return _contains_any_keyword(lower)


def _is_relevant_title(title: str) -> bool:
    lower = title.lower()
    if "capcut" in lower or "video editing" in lower:
        return True
    return _contains_any_keyword(lower)


def _contains_any_keyword(text: str) -> bool:
    for term in config.KEYWORD_EXPANSION_TERMS:
        if term in text:
            return True
    for app in config.COMPARISON_TARGETS:
        if app.lower() in text:
            return True
    return False
