"""Verify generate_article works correctly via template fallback."""
import sys, os
sys.path.insert(0, r"G:\Capcut Alerts App")

# Force template fallback by removing API keys temporarily
os.environ["GEMINI_API_KEYS"] = ""
os.environ["GEMINI_API_KEY"] = ""
import importlib
import config
importlib.reload(config)

from writer.article_generator import generate_article

opportunity = {
    "topic_key": "topic-1",
    "query": "capcut export settings for tiktok",
    "slug": "capcut-export-settings-for-tiktok",
    "bucket": "how_to",
    "score": 72,
    "title": "CapCut Export Settings for TikTok: Complete Guide",
    "brief": "Primary angle: how to. Answer search intent fast and add internal links.",
}
existing_pages = [
    {"url": "https://capcutpro-apks.com/capcut-best-settings/", "slug": "capcut-best-settings", "title": "CapCut Best Settings"},
    {"url": "https://capcutpro-apks.com/capcut-no-watermark-explained/", "slug": "capcut-no-watermark-explained", "title": "CapCut No Watermark Explained"},
    {"url": "https://capcutpro-apks.com/capcut-ban-status/", "slug": "capcut-ban-status", "title": "CapCut Ban Status"},
]

article = generate_article(opportunity, existing_pages)

print(f"meta_title: {article['meta_title']!r}")
print(f"meta_description: {article['meta_description']!r}")
print(f"focus_keywords count: {len(article['focus_keywords'])}")
print(f"faq_count: {article['faq_count']}")
print(f"faq_schema has ld+json: {'application/ld+json' in article.get('faq_schema', '')}")
print(f"has internal link: {'<a href=\"https://capcutpro-apks.com/' in article['content']}")

# Count ld+json blocks in final content
import re
ld_blocks = re.findall(r'<script type="application/ld\+json">', article["content"])
print(f"JSON-LD blocks in content: {len(ld_blocks)}")

# Check all assertions from the test
assertions = [
    ("meta_title not empty", bool(article["meta_title"])),
    ("meta_description not empty", bool(article["meta_description"])),
    ("focus_keywords >= 4", len(article["focus_keywords"]) >= 4),
    ("faq_count >= 1", article["faq_count"] >= 1),
    ("faq_schema has ld+json", "application/ld+json" in article.get("faq_schema", "")),
    ("internal link present", '<a href="https://capcutpro-apks.com/' in article["content"]),
]
all_ok = True
for name, result in assertions:
    status = "PASS" if result else "FAIL"
    if not result: all_ok = False
    print(f"  [{status}] {name}")
print(f"\nAll assertions pass: {all_ok}")
