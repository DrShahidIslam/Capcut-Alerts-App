"""
Trend and autocomplete discovery for CapCut queries.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from urllib.parse import quote

import requests

import config

logger = logging.getLogger(__name__)

MAX_INTEREST_BATCH = 5
MAX_INTEREST_QUERIES = 20


def fetch_trend_topics() -> list[dict]:
    topics: list[dict] = []
    topics.extend(_fetch_google_suggest())
    topics.extend(_fetch_pytrends_related())
    topics.extend(_fetch_pytrends_trending())
    topics = _dedupe_topics(topics)
    topics = _annotate_with_interest(topics)
    return topics


def _fetch_google_suggest() -> list[dict]:
    queries = []
    for seed in config.SEED_TOPICS[:10]:
        try:
            url = (
                "https://suggestqueries.google.com/complete/search"
                f"?client=firefox&hl=en&q={quote(seed)}"
            )
            response = requests.get(url, timeout=10)
            data = response.json()
            for suggestion in data[1][:8]:
                queries.append(
                    {
                        "query": suggestion,
                        "source": "google_suggest",
                        "signals": ["autocomplete"],
                        "freshness": 0.8,
                        "volume": 0,
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
        for batch_seed in ("capcut", "capcut template", "capcut pro", "video editing app", "capcut effects"):
            pytrends.build_payload([batch_seed], timeframe="today 3-m", geo=config.SITE_COUNTRY)
            related = pytrends.related_queries()
            bucket = related.get(batch_seed, {})
            for frame_name in ("top", "rising"):
                frame = bucket.get(frame_name)
                if frame is None:
                    continue
                for _, row in frame.head(10).iterrows():
                    query = str(row.get("query", "")).strip()
                    if query:
                        volume = int(row.get("value", 0)) if str(row.get("value", "")).isdigit() else 0
                        results.append(
                            {
                                "query": query,
                                "source": f"pytrends_{frame_name}",
                                "signals": [frame_name],
                                "freshness": 1.0 if frame_name == "rising" else 0.75,
                                "volume": volume,
                            }
                        )
    except Exception as exc:
        logger.debug("Pytrends discovery failed: %s", exc)
    return results


def _fetch_pytrends_trending() -> list[dict]:
    try:
        from pytrends.request import TrendReq
    except Exception:
        return []

    results = []
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        trending = pytrends.trending_searches(pn=config.SITE_COUNTRY.lower())
        for _, row in trending.head(30).iterrows():
            query = str(row[0]).strip()
            if not query:
                continue
            lower = query.lower()
            if "capcut" not in lower and "video" not in lower:
                continue
            results.append(
                {
                    "query": query,
                    "source": "pytrends_trending",
                    "signals": ["trending"],
                    "freshness": 0.95,
                    "volume": 0,
                }
            )
    except Exception as exc:
        logger.debug("Pytrends trending failed: %s", exc)
    return results


def _dedupe_topics(topics: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    for topic in topics:
        query = str(topic.get("query", "")).strip()
        if not query:
            continue
        key = query.lower()
        if key not in deduped:
            deduped[key] = topic
            continue
        existing = deduped[key]
        existing["signals"] = sorted(set(existing.get("signals", []) + topic.get("signals", [])))
        existing["freshness"] = max(existing.get("freshness", 0), topic.get("freshness", 0))
        existing["volume"] = max(existing.get("volume", 0), topic.get("volume", 0))
    return list(deduped.values())


def _annotate_with_interest(topics: list[dict]) -> list[dict]:
    try:
        from pytrends.request import TrendReq
    except Exception:
        return topics

    queries = [topic["query"] for topic in topics if topic.get("query")]
    if not queries:
        return topics

    # Prioritize already trending/rising topics for interest checks.
    queries = sorted(
        queries,
        key=lambda q: ("rising" not in q.lower(), q),
    )
    queries = queries[:MAX_INTEREST_QUERIES]

    trend_client = TrendReq(hl="en-US", tz=0)
    interest_data: dict[str, dict] = {}

    for start in range(0, len(queries), MAX_INTEREST_BATCH):
        batch = queries[start : start + MAX_INTEREST_BATCH]
        try:
            trend_client.build_payload(batch, timeframe="today 3-m", geo=config.SITE_COUNTRY)
            frame = trend_client.interest_over_time()
            if frame is None or frame.empty:
                continue
            for keyword in batch:
                if keyword not in frame:
                    continue
                series = frame[keyword].dropna()
                if series.empty:
                    continue
                avg = float(series.mean())
                recent = series.tail(7).mean() if len(series) >= 7 else series.mean()
                past = series.head(7).mean() if len(series) >= 14 else series.mean()
                momentum = 0.0
                if past:
                    momentum = (recent - past) / max(past, 1.0)
                interest_data[keyword.lower()] = {
                    "avg": int(avg),
                    "momentum": momentum,
                }
        except Exception as exc:
            logger.debug("Pytrends interest failed for batch %s: %s", batch, exc)

    for topic in topics:
        key = str(topic.get("query", "")).strip().lower()
        if key not in interest_data:
            continue
        metrics = interest_data[key]
        topic["volume"] = max(topic.get("volume", 0), metrics.get("avg", 0))
        if metrics.get("momentum", 0) >= 0.15:
            topic["signals"] = sorted(set(topic.get("signals", []) + ["momentum"]))
            topic["freshness"] = max(topic.get("freshness", 0), 0.9)
    return topics
