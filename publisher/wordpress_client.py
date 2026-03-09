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
    if not _credentials_configured():
        logger.info("WordPress credentials are not configured; skipping publish.")
        return None

    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": article.get("meta_title") or article["title"],
        "slug": article["slug"],
        "status": status or config.WP_DEFAULT_STATUS,
        "content": article["content"],
        "excerpt": article.get("meta_description") or article.get("excerpt", ""),
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


def test_connection() -> dict:
    configured = _credentials_configured()
    result = {
        "service": "wordpress",
        "configured": configured,
        "ok": False,
        "detail": "",
    }
    if not configured:
        result["detail"] = "Missing or placeholder WP_URL, WP_USERNAME, or WP_APP_PASSWORD"
        return result

    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/users/me"
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    try:
        response = requests.get(endpoint, headers=headers, timeout=20)
        if response.status_code >= 300:
            result["detail"] = f"HTTP {response.status_code}: {response.text[:180]}"
            return result
        payload = response.json()
        result["ok"] = True
        result["detail"] = f"Authenticated as {payload.get('name') or payload.get('slug') or 'unknown user'}"
        return result
    except Exception as exc:
        result["detail"] = str(exc)
        return result


def _credentials_configured() -> bool:
    if not config.WP_URL or not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        return False
    placeholders = {
        "your-wordpress-username",
        "your-wordpress-app-password",
        "example",
    }
    return config.WP_USERNAME.strip().lower() not in placeholders and config.WP_APP_PASSWORD.strip().lower() not in placeholders
