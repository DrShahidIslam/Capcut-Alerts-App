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
            if "capcut" not in url.lower():
                continue
            slug = urlparse(url).path.strip("/").replace("-", " ")
            if slug:
                topics.append(
                    {
                        "query": slug,
                        "source": "competitor_sitemap",
                        "signals": ["competitor-covered"],
                        "freshness": 0.65,
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
            lower = title.lower()
            if "capcut" not in lower and "video editing" not in lower:
                continue
            topics.append(
                {
                    "query": title,
                    "source": "news_feed",
                    "signals": ["fresh-news"],
                    "freshness": 0.9,
                }
            )
    except Exception as exc:
        logger.debug("Feed parse failed for %s: %s", feed_url, exc)
    return topics
