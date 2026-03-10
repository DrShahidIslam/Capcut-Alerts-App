"""
Fetch existing site URLs from config and optional XML sitemaps.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

import config
from database.db import get_connection

logger = logging.getLogger(__name__)


def fetch_existing_site_pages() -> list[dict]:
    pages = [_page_from_url(url) for url in config.EXISTING_SITE_URLS]
    pages.extend(_load_local_inventory())
    sitemap_urls = [
        f"{config.SITE_URL.rstrip('/')}/post-sitemap.xml",
        f"{config.SITE_URL.rstrip('/')}/page-sitemap.xml",
        f"{config.SITE_URL.rstrip('/')}/sitemap_index.xml",
    ]
    for sitemap_url in sitemap_urls:
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code != 200 or not response.text.strip():
                continue
            pages.extend(_parse_sitemap(response.text))
        except Exception as exc:
            logger.debug("Sitemap fetch failed for %s: %s", sitemap_url, exc)
    deduped = {}
    for page in pages:
        deduped[page["url"]] = page
    return list(deduped.values())


def _parse_sitemap(xml_text: str) -> list[dict]:
    pages = []
    root = ElementTree.fromstring(xml_text)
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}")[0] + "}"
    for url_node in root.findall(f".//{namespace}url"):
        loc = url_node.findtext(f"{namespace}loc", default="").strip()
        lastmod = url_node.findtext(f"{namespace}lastmod", default="").strip()
        if loc:
            pages.append(_page_from_url(loc, lastmod=lastmod))
    for sitemap_node in root.findall(f".//{namespace}sitemap"):
        loc = sitemap_node.findtext(f"{namespace}loc", default="").strip()
        if not loc:
            continue
        try:
            nested = requests.get(loc, timeout=10)
            if nested.status_code == 200 and nested.text.strip():
                pages.extend(_parse_sitemap(nested.text))
        except Exception as exc:
            logger.debug("Nested sitemap fetch failed for %s: %s", loc, exc)
    return pages


def _page_from_url(url: str, lastmod: str = "") -> dict:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    slug = parsed.path.strip("/")
    return {
        "url": normalized,
        "slug": slug or "home",
        "title": slug.replace("-", " ").title() if slug else "Home",
        "updated_at": lastmod,
    }


def _normalize_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    base = config.SITE_URL.rstrip("/")
    return f"{base}/{url.lstrip('/')}"


def _load_local_inventory() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT url, slug, title, updated_at FROM site_inventory").fetchall()
    finally:
        conn.close()
    pages = []
    for row in rows:
        pages.append(
            {
                "url": _normalize_url(row["url"]),
                "slug": row["slug"] or "home",
                "title": row["title"] or (row["slug"].replace("-", " ").title() if row["slug"] else "Home"),
                "updated_at": row["updated_at"] or "",
            }
        )
    return pages
