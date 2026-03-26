"""
Telegram utilities for alerts, previews, and approval actions.
"""
from __future__ import annotations

import json
import logging
import time

import requests

import config

logger = logging.getLogger(__name__)


def send_opportunity_alert(opportunity: dict) -> int | None:
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Write Draft", "callback_data": f"draft:{opportunity['topic_key']}"},
                {"text": "Ignore", "callback_data": f"ignore:{opportunity['topic_key']}"},
            ]
        ]
    }
    lines = [
        "CapCut content opportunity",
        "------------------------------",
        f"Title: {opportunity['title']}",
        f"Keyword: {opportunity['query']}",
        f"Bucket: {opportunity['bucket']}",
        f"Score: {opportunity['score']}",
        f"Sources: {', '.join(opportunity['sources'])}",
        f"Signals: {', '.join(opportunity['signals'])}",
        "",
        opportunity["brief"],
    ]
    return _send_message("\n".join(lines), reply_markup=keyboard)


def send_article_preview(article: dict) -> int | None:
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve Draft", "callback_data": f"approve:{article['topic_key']}"},
                {"text": "Publish Live", "callback_data": f"publish:{article['topic_key']}"},
            ],
            [
                {"text": "Reject", "callback_data": f"reject:{article['topic_key']}"},
            ],
        ]
    }
    preview = _plain_preview(article["content"])
    fallback_warning = ""
    if article.get("is_fallback"):
        fallback_warning = "\nLow confidence: template fallback was used."

    quality = article.get("quality_check") or {}
    issue_line = ""
    warning_line = ""
    if quality.get("issues"):
        issue_line = f"\nBlocking issues: {' | '.join(quality['issues'][:3])}"
    if quality.get("warnings"):
        warning_line = f"\nWarnings: {' | '.join(quality['warnings'][:3])}"

    source_quality = article.get("source_quality") or {}
    source_line = (
        f"\nSources: {source_quality.get('source_count', 0)} "
        f"from {source_quality.get('unique_domain_count', 0)} domains"
    )

    text = (
        "CapCut article ready for review\n"
        "------------------------------\n"
        f"Title: {article['title']}\n"
        f"Meta title: {article.get('meta_title', '')}\n"
        f"Slug: {article['slug']}\n"
        f"Words: {article['word_count']}\n"
        f"Meta description: {article['meta_description']}\n"
        f"Focus keywords: {', '.join(article.get('focus_keywords', []))}\n"
        f"FAQ schema: {article.get('faq_count', 0)} items"
        f"{source_line}"
        f"{fallback_warning}"
        f"{issue_line}"
        f"{warning_line}\n\n"
        f"{preview}"
    )
    return _send_message(text[:3900], reply_markup=keyboard)


def send_status(text: str) -> int | None:
    return _send_message(text)


def get_updates(offset: int | None = None) -> list[dict]:
    data = {}
    if offset is not None:
        data["offset"] = offset
    response = _post("getUpdates", data)
    if not response:
        return []
    return response.get("result", [])


def answer_callback_query(callback_query_id: str, text: str) -> None:
    _post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text[:150]})


def test_connection() -> bool:
    result = _get("getMe")
    return bool(result and result.get("ok"))


def _send_message(text: str, reply_markup: dict | None = None) -> int | None:
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    response = _post("sendMessage", payload)
    if not response or not response.get("ok"):
        return None
    return response["result"]["message_id"]


def _plain_preview(html_content: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", html_content)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:900] + ("..." if len(text) > 900 else "")


def _base_url() -> str | None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return None
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def _post(method: str, data: dict) -> dict | None:
    base_url = _base_url()
    if not base_url:
        logger.info("Telegram is not configured; skipping message: %s", method)
        return None
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(f"{base_url}/{method}", data=data, timeout=20)
            return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning("Telegram call failed for %s on attempt %s: %s", method, attempt + 1, exc)
            time.sleep(1 + attempt)
    logger.warning("Telegram call failed for %s after retries: %s", method, last_error)
    return None


def _get(method: str) -> dict | None:
    base_url = _base_url()
    if not base_url:
        return None
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(f"{base_url}/{method}", timeout=20)
            return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning("Telegram call failed for %s on attempt %s: %s", method, attempt + 1, exc)
            time.sleep(1 + attempt)
    logger.warning("Telegram call failed for %s after retries: %s", method, last_error)
    return None
