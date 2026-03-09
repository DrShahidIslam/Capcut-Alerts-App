"""
Central configuration for the CapCut content pipeline.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "CapCut Content Alerts"
SITE_NAME = os.getenv("SITE_NAME", "CapCut Pro APKs")
SITE_URL = os.getenv("SITE_URL", "https://capcutpro-apks.com")
SITE_LANGUAGE = os.getenv("SITE_LANGUAGE", "en")
SITE_COUNTRY = os.getenv("SITE_COUNTRY", "US")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

WP_URL = os.getenv("WP_URL", SITE_URL.rstrip("/"))
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
WP_DEFAULT_STATUS = os.getenv("WP_DEFAULT_STATUS", "draft")
WP_DEFAULT_CATEGORY = os.getenv("WP_DEFAULT_CATEGORY", "Blog")

_gemini_keys_env = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
GEMINI_API_KEYS = [key.strip() for key in _gemini_keys_env.split(",") if key.strip()]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

LOG_FILE = os.getenv("LOG_FILE", "agent.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "180"))
MAX_ALERTS_PER_RUN = int(os.getenv("MAX_ALERTS_PER_RUN", "5"))
MAX_OPPORTUNITIES_PER_RUN = int(os.getenv("MAX_OPPORTUNITIES_PER_RUN", "25"))
MIN_OPPORTUNITY_SCORE = int(os.getenv("MIN_OPPORTUNITY_SCORE", "35"))
MAX_BUCKET_SHARE = float(os.getenv("MAX_BUCKET_SHARE", "0.4"))
MAX_COMPARISON_SHARE = float(os.getenv("MAX_COMPARISON_SHARE", "0.24"))
DIVERSITY_PENALTY_PER_BUCKET = int(os.getenv("DIVERSITY_PENALTY_PER_BUCKET", "5"))

KEYWORD_EXPANSION_TERMS = [
    "apk",
    "mod apk",
    "download",
    "latest version",
    "old version",
    "pc",
    "ios",
    "android",
    "ban",
    "safe",
    "legal",
    "without watermark",
    "template",
    "template trend",
    "pro vs free",
    "vs canva",
    "vs vn",
    "vs inshot",
    "export settings",
    "best settings",
    "fix error",
    "login issue",
    "not working",
    "black screen",
    "lag",
    "auto captions",
    "ai tools",
    "remove background",
    "slow motion",
    "text effects",
]

SEED_TOPICS = [
    "capcut pro apk download",
    "capcut for pc",
    "capcut vs canva",
    "capcut vs inshot",
    "capcut vs vn editor",
    "how to use capcut templates",
    "capcut export settings for youtube",
    "capcut export settings for tiktok",
    "capcut no internet connection fix",
    "capcut login problem fix",
    "capcut ban status",
    "capcut watermark removal",
    "capcut auto captions guide",
    "capcut ai video generator",
    "capcut old version",
    "capcut mod apk safety",
    "capcut not available in country",
    "capcut black screen fix",
    "capcut lag fix",
    "capcut best settings",
    "capcut transitions guide",
    "capcut text animation guide",
]

COMPARISON_TARGETS = [
    "Canva",
    "InShot",
    "VN",
    "KineMaster",
    "Alight Motion",
    "Premiere Rush",
    "Filmora",
]

COMPETITOR_SITEMAPS = [
    "https://capcutmodapk.id/sitemap_index.xml",
    "https://capcutapkpro.com/post-sitemap.xml",
    "https://capcutdownload.net/post-sitemap.xml",
]

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=CapCut&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22video%20editing%20app%22&hl=en-US&gl=US&ceid=US:en",
]

ARTICLE_MIN_WORDS = int(os.getenv("ARTICLE_MIN_WORDS", "1200"))
ARTICLE_MAX_WORDS = int(os.getenv("ARTICLE_MAX_WORDS", "2200"))
ARTICLE_TONE = os.getenv("ARTICLE_TONE", "helpful, practical, and SEO-focused")
DEFAULT_FOCUS_KEYWORD_COUNT = int(os.getenv("DEFAULT_FOCUS_KEYWORD_COUNT", "5"))

REPORTS_DIR = os.getenv("REPORTS_DIR", os.path.join("data", "reports"))
EXPORTS_DIR = os.getenv("EXPORTS_DIR", os.path.join("data", "exports"))
SCHEDULER_DIR = os.getenv("SCHEDULER_DIR", os.path.join("data", "scheduler"))
WINDOWS_TASK_NAME = os.getenv("WINDOWS_TASK_NAME", "CapCut Content Alerts")
WINDOWS_TASK_INTERVAL_HOURS = int(os.getenv("WINDOWS_TASK_INTERVAL_HOURS", "3"))

EXISTING_SITE_URLS = [
    "https://capcutpro-apks.com/",
    "https://capcutpro-apks.com/capcut-ban-status/",
    "https://capcutpro-apks.com/capcut-features-how-to-use/",
    "https://capcutpro-apks.com/capcut-templates-new-trends/",
    "https://capcutpro-apks.com/install-capcut-pro-apk-fix-errors/",
    "https://capcutpro-apks.com/capcut-no-watermark-explained/",
    "https://capcutpro-apks.com/capcut-best-settings/",
    "https://capcutpro-apks.com/capcut-pro-apk-safety-privacy-legal/",
    "https://capcutpro-apks.com/terms-and-conditions/",
    "https://capcutpro-apks.com/privacy-policy/",
    "https://capcutpro-apks.com/dmca-copyright-policy/",
    "https://capcutpro-apks.com/disclaimer/",
    "https://capcutpro-apks.com/contact-us/",
    "https://capcutpro-apks.com/about-us/",
]

EXCLUDE_SLUG_HINTS = {
    "privacy-policy",
    "terms-and-conditions",
    "dmca-copyright-policy",
    "disclaimer",
    "contact-us",
    "about-us",
}

STRATEGIC_BUCKET_BOOSTS = {
    "comparison": 18,
    "how_to": 14,
    "fix": 16,
    "trend": 12,
    "download": 8,
    "safety": 10,
}
