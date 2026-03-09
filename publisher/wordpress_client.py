"""
WordPress publishing helpers.
"""
from __future__ import annotations

import base64
import logging

import requests

import config

logger = logging.getLogger(__name__)


def create_post(article: dict, status: str | None = None) -> dict | None:
    if not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        logger.info("WordPress credentials are not configured; skipping publish.")
        return None

    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": article["title"],
        "slug": article["slug"],
        "status": status or config.WP_DEFAULT_STATUS,
        "content": article["content"],
        "excerpt": article.get("excerpt", ""),
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        if response.status_code >= 300:
            logger.warning("WordPress rejected post: %s %s", response.status_code, response.text[:500])
            return None
        return response.json()
    except Exception as exc:
        logger.warning("WordPress publish failed: %s", exc)
        return None
