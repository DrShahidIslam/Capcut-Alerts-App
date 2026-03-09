"""
Admin reporting helpers for opportunities and draft history.
"""
from __future__ import annotations

import csv
import html
import json
import os
from datetime import datetime

import config


OPPORTUNITY_COLUMNS = [
    "query",
    "bucket",
    "score",
    "status",
    "source_count",
    "freshness",
    "sources",
    "updated_at",
]

DRAFT_COLUMNS = [
    "title",
    "slug",
    "status",
    "word_count",
    "meta_title",
    "focus_keywords",
    "updated_at",
    "wordpress_post_id",
]


def opportunity_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        rows.append(
            {
                "query": item.get("query", ""),
                "bucket": item.get("bucket", ""),
                "score": item.get("score", 0),
                "status": item.get("status", ""),
                "source_count": item.get("source_count", 0),
                "freshness": item.get("freshness", ""),
                "sources": ", ".join(item.get("sources", [])),
                "updated_at": item.get("updated_at", ""),
            }
        )
    return rows


def draft_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        rows.append(
            {
                "title": item.get("title", ""),
                "slug": item.get("slug", ""),
                "status": item.get("status", ""),
                "word_count": item.get("word_count", 0),
                "meta_title": item.get("meta_title") or item.get("seo_title", ""),
                "focus_keywords": ", ".join(item.get("focus_keywords", [])),
                "updated_at": item.get("updated_at") or item.get("created_at", ""),
                "wordpress_post_id": item.get("wordpress_post_id", ""),
            }
        )
    return rows


def render_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "No records found."
    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = min(max(widths[column], len(str(row.get(column, "")))), 48)

    def _cell(column: str, value: object) -> str:
        text = str(value)
        if len(text) > widths[column]:
            text = text[: widths[column] - 1] + "…"
        return text.ljust(widths[column])

    lines = [" | ".join(column.ljust(widths[column]) for column in columns)]
    lines.append("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        lines.append(" | ".join(_cell(column, row.get(column, "")) for column in columns))
    return "\n".join(lines)


def export_dataset(name: str, rows: list[dict], fmt: str, output_path: str | None = None) -> str:
    fmt = fmt.lower()
    if fmt == "table":
        raise ValueError("Table format is for stdout only.")
    if output_path is None:
        base_dir = config.REPORTS_DIR if fmt == "html" else config.EXPORTS_DIR
        output_path = os.path.join(base_dir, f"{name}.{fmt}")
    _ensure_parent(output_path)
    if fmt == "json":
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        columns = list(rows[0].keys()) if rows else []
        with open(output_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "html":
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(_render_html_report(name, rows))
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    return output_path


def _render_html_report(name: str, rows: list[dict]) -> str:
    columns = list(rows[0].keys()) if rows else []
    headers = "".join(f"<th>{html.escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
        body += f"<tr>{cells}</tr>"
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<title>{html.escape(name.title())}</title>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: Georgia, 'Times New Roman', serif; background: linear-gradient(135deg, #f7f1e8, #fefcf7); color: #2f2419; margin: 0; padding: 32px; }}
main {{ max-width: 1200px; margin: 0 auto; background: rgba(255,255,255,0.84); border: 1px solid #dccdb8; border-radius: 18px; padding: 28px; box-shadow: 0 18px 60px rgba(91, 63, 28, 0.10); }}
h1 {{ margin-top: 0; font-size: 2rem; }}
p.meta {{ color: #71553b; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 0.95rem; }}
th, td {{ border-bottom: 1px solid #e7dccd; text-align: left; padding: 12px 10px; vertical-align: top; }}
th {{ background: #f2e7d8; }}
tr:nth-child(even) td {{ background: #fcf7f0; }}
code {{ font-family: Consolas, monospace; }}
</style>
</head>
<body>
<main>
<h1>{html.escape(name.replace('_', ' ').title())}</h1>
<p class=\"meta\">Generated {generated_at}</p>
<table>
<thead><tr>{headers}</tr></thead>
<tbody>{body}</tbody>
</table>
</main>
</body>
</html>"""


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
