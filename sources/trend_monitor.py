"""
Trend and autocomplete discovery for CapCut queries.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests

import config

logger = logging.getLogger(__name__)


def fetch_trend_topics() -> list[dict]:
    topics = []
    topics.extend(_fetch_google_suggest())
    topics.extend(_fetch_pytrends_related())
    return topics


def _fetch_google_suggest() -> list[dict]:
    queries = []
    for seed in config.SEED_TOPICS[:8]:
        try:
            url = (
                "https://suggestqueries.google.com/complete/search"
                f"?client=firefox&hl=en&q={quote(seed)}"
            )
            response = requests.get(url, timeout=10)
            data = response.json()
            for suggestion in data[1][:6]:
                queries.append(
                    {
                        "query": suggestion,
                        "source": "google_suggest",
                        "signals": ["autocomplete"],
                        "freshness": 0.8,
                    }
                )
        except Exception as exc:
            logger.debug("Google suggest failed for %s: %s", seed, exc)
    return queries


def _fetch_pytrends_related() -> list[dict]:
    try:
        from pytrends.request import TrendReq
    except Exception:
        return []

    results = []
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        for batch_seed in ("capcut", "capcut template", "capcut pro", "video editing app"):
            pytrends.build_payload([batch_seed], timeframe="today 3-m", geo=config.SITE_COUNTRY)
            related = pytrends.related_queries()
            bucket = related.get(batch_seed, {})
            for frame_name in ("top", "rising"):
                frame = bucket.get(frame_name)
                if frame is None:
                    continue
                for _, row in frame.head(8).iterrows():
                    query = str(row.get("query", "")).strip()
                    if query:
                        results.append(
                            {
                                "query": query,
                                "source": f"pytrends_{frame_name}",
                                "signals": [frame_name],
                                "freshness": 1.0 if frame_name == "rising" else 0.75,
                            }
                        )
    except Exception as exc:
        logger.debug("Pytrends discovery failed: %s", exc)
    return results
