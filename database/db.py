"""
SQLite helpers for topic discovery, alert tracking, and pending drafts.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS site_inventory (
            url TEXT PRIMARY KEY,
            slug TEXT,
            title TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT UNIQUE,
            topic_json TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT NOT NULL,
            telegram_message_id TEXT,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS generated_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT UNIQUE,
            article_json TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            wordpress_post_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def upsert_site_url(conn: sqlite3.Connection, url: str, slug: str, title: str = "", updated_at: str = "") -> None:
    conn.execute(
        """
        INSERT INTO site_inventory (url, slug, title, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            slug = excluded.slug,
            title = excluded.title,
            updated_at = excluded.updated_at
        """,
        (url, slug, title, updated_at),
    )
    conn.commit()


def get_existing_slugs(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT slug FROM site_inventory WHERE slug IS NOT NULL AND slug != ''").fetchall()
    return {row["slug"] for row in rows}


def upsert_opportunity(conn: sqlite3.Connection, topic: dict) -> None:
    payload = json.dumps(topic, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO opportunities (topic_key, topic_json, score, status, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(topic_key) DO UPDATE SET
            topic_json = excluded.topic_json,
            score = excluded.score,
            updated_at = excluded.updated_at
        """,
        (
            topic["topic_key"],
            payload,
            int(topic.get("score", 0)),
            topic.get("status", "new"),
            _now_iso(),
        ),
    )
    conn.commit()


def fetch_top_opportunities(conn: sqlite3.Connection, limit: int = 10, min_score: int = 0) -> list[dict]:
    rows = conn.execute(
        """
        SELECT topic_json
        FROM opportunities
        WHERE score >= ?
          AND status IN ('new')
        ORDER BY score DESC, updated_at DESC
        LIMIT ?
        """,
        (min_score, limit),
    ).fetchall()
    return [json.loads(row["topic_json"]) for row in rows]


def get_opportunity(conn: sqlite3.Connection, topic_key: str) -> dict | None:
    row = conn.execute(
        "SELECT topic_json FROM opportunities WHERE topic_key = ?",
        (topic_key,),
    ).fetchone()
    return json.loads(row["topic_json"]) if row else None


def update_opportunity_status(conn: sqlite3.Connection, topic_key: str, status: str) -> None:
    conn.execute(
        "UPDATE opportunities SET status = ?, updated_at = ? WHERE topic_key = ?",
        (status, _now_iso(), topic_key),
    )
    conn.commit()


def record_alert(conn: sqlite3.Connection, topic_key: str, message_id: str | int | None) -> None:
    conn.execute(
        "INSERT INTO alerts (topic_key, telegram_message_id) VALUES (?, ?)",
        (topic_key, str(message_id or "")),
    )
    conn.execute(
        "UPDATE opportunities SET status = 'alerted', updated_at = ? WHERE topic_key = ?",
        (_now_iso(), topic_key),
    )
    conn.commit()


def save_generated_article(conn: sqlite3.Connection, topic_key: str, article: dict, status: str = "pending") -> None:
    payload = json.dumps(article, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO generated_articles (topic_key, article_json, status, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(topic_key) DO UPDATE SET
            article_json = excluded.article_json,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (topic_key, payload, status, _now_iso()),
    )
    conn.commit()


def get_generated_article(conn: sqlite3.Connection, topic_key: str) -> dict | None:
    row = conn.execute(
        "SELECT article_json FROM generated_articles WHERE topic_key = ?",
        (topic_key,),
    ).fetchone()
    return json.loads(row["article_json"]) if row else None


def mark_article_status(
    conn: sqlite3.Connection,
    topic_key: str,
    status: str,
    wordpress_post_id: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE generated_articles
        SET status = ?, wordpress_post_id = COALESCE(?, wordpress_post_id), updated_at = ?
        WHERE topic_key = ?
        """,
        (status, wordpress_post_id, _now_iso(), topic_key),
    )
    conn.execute(
        "UPDATE opportunities SET status = ?, updated_at = ? WHERE topic_key = ?",
        (status, _now_iso(), topic_key),
    )
    conn.commit()


def cleanup_old_rows(conn: sqlite3.Connection, days: int = 30) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    conn.execute("DELETE FROM alerts WHERE sent_at < ?", (cutoff_iso,))
    conn.execute("DELETE FROM opportunities WHERE updated_at < ? AND status IN ('rejected', 'published')", (cutoff_iso,))
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
