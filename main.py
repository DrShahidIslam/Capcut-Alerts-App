"""
CapCut content pipeline:
discover -> alert -> draft -> approve -> publish.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import config
from admin.reporting import (
    DRAFT_COLUMNS,
    OPPORTUNITY_COLUMNS,
    draft_rows,
    export_dataset,
    opportunity_rows,
    render_table,
)
from database.db import (
    cleanup_old_rows,
    fetch_draft_history,
    fetch_top_opportunities,
    get_connection,
    get_existing_slugs,
    get_generated_article,
    get_opportunity,
    list_generated_articles,
    list_opportunities,
    mark_article_status,
    record_alert,
    save_generated_article,
    update_opportunity_status,
    upsert_opportunity,
    upsert_site_url,
)
from detection.opportunity_detector import detect_opportunities
from notifications.telegram_bot import (
    answer_callback_query,
    get_updates,
    send_article_preview,
    send_opportunity_alert,
    send_status,
    test_connection as test_telegram_connection,
)
from publisher.wordpress_client import create_post, test_connection as test_wordpress_connection
from scheduler.windows_task import install_windows_task, write_scheduler_setup
from sources.competitor_monitor import fetch_competitor_topics
from sources.seed_monitor import fetch_seed_topics
from sources.site_inventory import fetch_existing_site_pages
from sources.trend_monitor import fetch_trend_topics
from writer.article_generator import generate_article, get_generation_health

STATE_FILE = os.path.join(os.path.dirname(__file__), "pending_state.json")

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("CapCutPipeline")

_update_offset = None


def run_discovery() -> list[dict]:
    logger.info("Starting CapCut opportunity discovery")
    conn = get_connection()
    existing_pages = fetch_existing_site_pages()
    for page in existing_pages:
        upsert_site_url(conn, page["url"], page["slug"], page.get("title", ""), page.get("updated_at", ""))
    existing_slugs = get_existing_slugs(conn)

    bundles = [
        fetch_seed_topics(),
        fetch_trend_topics(),
        fetch_competitor_topics(),
    ]
    opportunities = detect_opportunities(existing_slugs, bundles)
    for item in opportunities:
        upsert_opportunity(conn, item)
    cleanup_old_rows(conn)
    conn.close()
    logger.info("Discovery completed with %s ranked opportunities", len(opportunities))
    return opportunities


def send_top_alerts() -> int:
    conn = get_connection()
    opportunities = fetch_top_opportunities(conn, limit=config.MAX_ALERTS_PER_RUN, min_score=config.MIN_OPPORTUNITY_SCORE)
    sent = 0
    for opportunity in opportunities:
        message_id = send_opportunity_alert(opportunity)
        if message_id:
            record_alert(conn, opportunity["topic_key"], message_id)
            sent += 1
        time.sleep(1)
    conn.close()
    return sent


def handle_updates() -> None:
    global _update_offset
    updates = get_updates(offset=_update_offset)
    if not updates:
        return
    for update in updates:
        _update_offset = update["update_id"] + 1
        callback = update.get("callback_query")
        if not callback:
            continue
        data = callback.get("data", "")
        callback_id = callback.get("id")
        action, _, topic_key = data.partition(":")
        if callback_id:
            answer_callback_query(callback_id, f"{action} received")
        if not topic_key:
            continue
        if action == "draft":
            _handle_generate(topic_key)
        elif action == "approve":
            _handle_publish(topic_key, "draft")
        elif action == "publish":
            _handle_publish(topic_key, "publish")
        elif action == "reject":
            _handle_reject(topic_key)
        elif action == "ignore":
            _handle_ignore(topic_key)


def _handle_generate(topic_key: str) -> None:
    conn = get_connection()
    opportunity = get_opportunity(conn, topic_key)
    existing_pages = fetch_existing_site_pages()
    if not opportunity:
        send_status(f"Topic {topic_key} was not found in the queue.")
        conn.close()
        return
    article = generate_article(opportunity, existing_pages)
    save_generated_article(conn, topic_key, article, status="pending")
    update_opportunity_status(conn, topic_key, "pending")
    _save_pending_state(article)
    send_article_preview(article)
    conn.close()


def _handle_publish(topic_key: str, status: str) -> None:
    conn = get_connection()
    article = get_generated_article(conn, topic_key)
    if not article:
        send_status("No generated article was found for this topic.")
        conn.close()
        return
    result = create_post(article, status=status)
    if result:
        post_url = (result.get("link") or "").strip()
        if not post_url:
            base = config.WP_URL.rstrip("/")
            slug = (article.get("slug") or "").strip("/")
            if slug:
                post_url = f"{base}/{slug}/"
        if status == "publish" and post_url:
            parsed = urlparse(post_url)
            slug = parsed.path.strip("/") or (article.get("slug") or "home")
            upsert_site_url(conn, post_url, slug, article.get("title", ""), datetime.now(timezone.utc).isoformat())
        mark_article_status(conn, topic_key, "published" if status == "publish" else "approved", result.get("id"))
        send_status(
            f"WordPress {'published' if status == 'publish' else 'saved a draft for'}: "
            f"{article['title']}\n{result.get('link', config.WP_URL)}"
        )
        _clear_pending_state()
    else:
        send_status(
            f"Article approved for {status}, but WordPress is not configured or rejected the request. "
            f"The draft remains stored locally for topic {topic_key}."
        )
        mark_article_status(conn, topic_key, "approved")
    conn.close()


def _handle_reject(topic_key: str) -> None:
    conn = get_connection()
    mark_article_status(conn, topic_key, "rejected")
    update_opportunity_status(conn, topic_key, "rejected")
    _clear_pending_state()
    send_status(f"Rejected article for topic {topic_key}.")
    conn.close()


def _handle_ignore(topic_key: str) -> None:
    conn = get_connection()
    update_opportunity_status(conn, topic_key, "ignored")
    send_status(f"Ignored topic {topic_key}.")
    conn.close()


def _save_pending_state(article: dict) -> None:
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "article": article,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _clear_pending_state() -> None:
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def run_service_checks() -> list[dict]:
    telegram_configured = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
    telegram_ok = test_telegram_connection() if telegram_configured else False
    checks = [
        {
            "service": "telegram",
            "configured": telegram_configured,
            "ok": telegram_ok,
            "detail": "Connected to Telegram bot API" if telegram_ok else (
                "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID" if not telegram_configured else "Telegram API request failed"
            ),
        },
        test_wordpress_connection(),
        get_generation_health(),
    ]
    return checks


def _handle_admin_view(view_name: str, limit: int, fmt: str, output_path: str | None) -> int:
    conn = get_connection()
    try:
        if view_name == "opportunities":
            rows = opportunity_rows(list_opportunities(conn, limit=limit))
            columns = OPPORTUNITY_COLUMNS
            dataset_name = "opportunities"
        else:
            rows = draft_rows(fetch_draft_history(conn, limit=limit))
            columns = DRAFT_COLUMNS
            dataset_name = "draft_history"
    finally:
        conn.close()

    if fmt == "table":
        print(render_table(rows, columns))
        return 0
    path = export_dataset(dataset_name, rows, fmt, output_path)
    print(f"Saved {view_name} {fmt} view to {path}")
    return 0


def _handle_export(dataset: str, limit: int, fmt: str, output_path: str | None) -> int:
    conn = get_connection()
    try:
        if dataset == "opportunities":
            rows = opportunity_rows(list_opportunities(conn, limit=limit))
        elif dataset == "drafts":
            rows = draft_rows(list_generated_articles(conn, limit=limit))
        else:
            rows = draft_rows(fetch_draft_history(conn, limit=limit))
    finally:
        conn.close()

    if fmt == "table":
        columns = OPPORTUNITY_COLUMNS if dataset == "opportunities" else DRAFT_COLUMNS
        print(render_table(rows, columns))
        return 0

    dataset_name = "draft_history" if dataset == "history" else dataset
    path = export_dataset(dataset_name, rows, fmt, output_path)
    print(f"Exported {dataset_name} to {path}")
    return 0


def _handle_scheduler_setup(install: bool) -> int:
    setup = write_scheduler_setup(config.SCHEDULER_DIR, config.WINDOWS_TASK_INTERVAL_HOURS)
    print(f"Run script: {setup['run_script']}")
    print(f"Install script: {setup['install_script']}")
    print(f"schtasks command: {setup['command_preview']}")
    if install:
        result = install_windows_task(setup["run_script"], setup["interval_hours"])
        print(result["detail"])
        return 0 if result["ok"] else 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CapCut content alerts pipeline")
    parser.add_argument("--once", action="store_true", help="Run discovery and alert once")
    parser.add_argument("--discover-only", action="store_true", help="Only refresh the opportunity queue")
    parser.add_argument("--handle-updates", action="store_true", help="Only process Telegram callbacks once")
    parser.add_argument("--test", action="store_true", help="Test external service configuration")
    parser.add_argument("--admin-view", choices=["opportunities", "drafts"], help="Show or export an admin view")
    parser.add_argument("--export", choices=["opportunities", "drafts", "history"], help="Export queue or draft datasets")
    parser.add_argument("--format", choices=["table", "json", "csv", "html"], default="table", help="Output format")
    parser.add_argument("--output", help="Optional output file path for exports or HTML views")
    parser.add_argument("--limit", type=int, default=50, help="Max records for admin or export commands")
    parser.add_argument("--write-scheduler-setup", action="store_true", help="Write Windows Task Scheduler helper scripts")
    parser.add_argument("--install-task-scheduler", action="store_true", help="Create or update the Windows scheduled task")
    args = parser.parse_args()

    if args.test:
        checks = run_service_checks()
        for check in checks:
            print(
                f"{check['service'].title()}: configured={check['configured']} ok={check['ok']} detail={check['detail']}"
            )
        return 0 if all(check["ok"] or not check["configured"] for check in checks) else 1

    if args.admin_view:
        return _handle_admin_view(args.admin_view, args.limit, args.format, args.output)

    if args.export:
        return _handle_export(args.export, args.limit, args.format, args.output)

    if args.write_scheduler_setup or args.install_task_scheduler:
        return _handle_scheduler_setup(install=args.install_task_scheduler)

    if args.discover_only:
        discovered = run_discovery()
        print(f"Discovered {len(discovered)} opportunities")
        return 0

    if args.handle_updates:
        handle_updates()
        return 0

    if args.once:
        discovered = run_discovery()
        sent = send_top_alerts()
        print(f"Discovered {len(discovered)} opportunities and sent {sent} alerts")
        return 0

    while True:
        run_discovery()
        send_top_alerts()
        handle_updates()
        logger.info("Sleeping for %s minutes", config.SCAN_INTERVAL_MINUTES)
        time.sleep(config.SCAN_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    raise SystemExit(main())





