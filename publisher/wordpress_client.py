"""WordPress publishing helpers.

This module publishes generated articles and attempts to populate:
- Category (default: Blog)
- RankMath SEO meta (title/description/focus keyword)
- Featured image (simple generated PNG)

If any optional step fails (category lookup, media upload, meta keys not enabled in REST),
we log and still publish the post content.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

try:
    from publisher.featured_image import render_featured_image_png
except Exception:  # pragma: no cover
    render_featured_image_png = None


_CATEGORY_CACHE: dict[str, int] = {}


def create_post(article: dict, status: str | None = None) -> dict | None:
    if not _credentials_configured():
        logger.info("WordPress credentials are not configured; skipping publish.")
        return None

    categories: list[int] = []
    if config.WP_DEFAULT_CATEGORY:
        category_id = _get_or_create_category_id(config.WP_DEFAULT_CATEGORY)
        if category_id:
            categories = [category_id]

    featured_media: int | None = None
    if config.WP_UPLOAD_FEATURED_IMAGE and render_featured_image_png is not None:
        try:
            png_bytes = render_featured_image_png(article.get("title") or article.get("meta_title") or "CapCut Guide")
            filename = f"{article.get('slug') or 'capcut-guide'}-featured.png"
            media = upload_media(
                filename=filename,
                content_bytes=png_bytes,
                mime_type="image/png",
                title=article.get("title") or "Featured image",
                alt_text=article.get("title") or "Featured image",
            )
            featured_media = int(media.get("id")) if media and media.get("id") is not None else None
        except Exception as exc:
            logger.warning("Featured image upload failed: %s", exc)

    meta: dict[str, Any] = {}
    if config.WP_SET_RANKMATH_META:
        focus_keywords = article.get("focus_keywords") or []
        if isinstance(focus_keywords, str):
            focus_value = focus_keywords
        elif isinstance(focus_keywords, list):
            focus_value = ", ".join(str(item) for item in focus_keywords if str(item).strip())
        else:
            focus_value = ""

        # RankMath commonly uses these meta keys. They may require show_in_rest enabled.
        meta = {
            "rank_math_title": article.get("meta_title") or article.get("seo_title") or article.get("title"),
            "rank_math_description": article.get("meta_description") or article.get("excerpt") or "",
            "rank_math_focus_keyword": focus_value,
        }

    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
    payload: dict[str, Any] = {
        "title": article.get("title") or article.get("meta_title"),
        "slug": article["slug"],
        "status": status or config.WP_DEFAULT_STATUS,
        "content": article["content"],
        "excerpt": article.get("excerpt") or article.get("meta_description") or "",
    }
    if categories:
        payload["categories"] = categories
    if featured_media is not None:
        payload["featured_media"] = featured_media
    if meta:
        payload["meta"] = meta

    try:
        response = _request("POST", endpoint, json=payload, timeout=30)\n        if response.status_code >= 300 and "meta" in payload:\n            logger.info("Post create rejected with meta; retrying without RankMath meta. HTTP %s", response.status_code)\n            retry_payload = {key: value for key, value in payload.items() if key != "meta"}\n            response = _request("POST", endpoint, json=retry_payload, timeout=30)\n        if response.status_code >= 300:\n            logger.warning("WordPress rejected post: %s %s", response.status_code, response.text[:500])\n            return None\n        return response.json()
    except Exception as exc:
        logger.warning("WordPress publish failed: %s", exc)
        return None


def upload_media(filename: str, content_bytes: bytes, mime_type: str, title: str = "", alt_text: str = "") -> dict | None:
    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    headers = _auth_headers(content_type=mime_type)
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    response = _request("POST", endpoint, headers=headers, data=content_bytes, timeout=60)
    if response.status_code >= 300:
        logger.warning("WordPress rejected media upload: %s %s", response.status_code, response.text[:300])
        return None

    media = response.json()
    media_id = media.get("id")
    if media_id and (title or alt_text):
        try:
            update_endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
            update_payload: dict[str, Any] = {}
            if title:
                update_payload["title"] = title
            if alt_text:
                update_payload["alt_text"] = alt_text
            _request("POST", update_endpoint, json=update_payload, timeout=30)
        except Exception as exc:
            logger.info("Media meta update failed (non-fatal): %s", exc)

    return media


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
    try:
        response = _request("GET", endpoint, timeout=20)
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


def _get_or_create_category_id(name: str) -> int | None:
    cache_key = (name or "").strip().lower()
    if not cache_key:
        return None
    if cache_key in _CATEGORY_CACHE:
        return _CATEGORY_CACHE[cache_key]

    category_id = _find_category_id(name)
    if category_id is None:
        category_id = _create_category(name)

    if category_id is not None:
        _CATEGORY_CACHE[cache_key] = category_id

    return category_id


def _find_category_id(name: str) -> int | None:
    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/categories"
    params = {"search": name, "per_page": 100}
    response = _request("GET", endpoint, params=params, timeout=30)
    if response.status_code >= 300:
        return None

    wanted = name.strip().lower()
    for item in response.json() or []:
        if (item.get("name") or "").strip().lower() == wanted:
            return int(item.get("id"))

    # Fall back to first match if any.
    items = response.json() or []
    if items:
        try:
            return int(items[0].get("id"))
        except Exception:
            return None
    return None


def _create_category(name: str) -> int | None:
    endpoint = f"{config.WP_URL.rstrip('/')}/wp-json/wp/v2/categories"
    payload = {"name": name}
    response = _request("POST", endpoint, json=payload, timeout=30)
    if response.status_code >= 300:
        logger.info("Category create failed (non-fatal): %s %s", response.status_code, response.text[:200])
        return None
    try:
        return int(response.json().get("id"))
    except Exception:
        return None


def _request(method: str, url: str, headers: dict[str, str] | None = None, **kwargs: Any) -> requests.Response:
    merged = _auth_headers() if headers is None else {**_auth_headers(), **headers}
    return requests.request(method, url, headers=merged, **kwargs)


def _auth_headers(content_type: str | None = None) -> dict[str, str]:
    token = base64.b64encode(f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _credentials_configured() -> bool:
    if not config.WP_URL or not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        return False
    placeholders = {
        "your-wordpress-username",
        "your-wordpress-app-password",
        "example",
    }
    return config.WP_USERNAME.strip().lower() not in placeholders and config.WP_APP_PASSWORD.strip().lower() not in placeholders

