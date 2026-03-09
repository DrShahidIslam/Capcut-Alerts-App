"""
Build high-intent topic opportunities from local seed terms.
"""
from __future__ import annotations

import config


def fetch_seed_topics() -> list[dict]:
    items = []
    for term in config.SEED_TOPICS:
        items.append(
            {
                "query": term,
                "source": "seed",
                "signals": ["core-topic"],
                "freshness": 0.6,
            }
        )
    for target in config.COMPARISON_TARGETS:
        items.append(
            {
                "query": f"capcut vs {target.lower()}",
                "source": "seed",
                "signals": ["comparison"],
                "freshness": 0.7,
            }
        )
    return items
