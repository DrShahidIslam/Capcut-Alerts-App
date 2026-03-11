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
WP_UPLOAD_FEATURED_IMAGE = os.getenv("WP_UPLOAD_FEATURED_IMAGE", "true").strip().lower() in {"1", "true", "yes", "y"}
WP_SET_RANKMATH_META = os.getenv("WP_SET_RANKMATH_META", "true").strip().lower() in {"1", "true", "yes", "y"}

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

# When running with --once, keep the process alive to handle Telegram callbacks
# (generate/approve/publish) before exiting.
ONCE_REPLY_WINDOW_SECONDS = int(os.getenv("ONCE_REPLY_WINDOW_SECONDS", "420"))  # 7 minutes
TELEGRAM_POLL_INTERVAL_SECONDS = int(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "5"))
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
    # --- New expansion terms for broader coverage ---
    "green screen",
    "keyframes",
    "speed ramp",
    "overlay",
    "chroma key",
    "voice over",
    "text to speech",
    "upscale",
    "resize",
    "crop",
    "slideshow",
    "subtitle",
    "music",
    "transition",
    "split",
    "merge",
    "reverse",
    "zoom",
    "pan",
    "cinematic",
    "blur",
    "stabilize",
]

SEED_TOPICS = [
    # --- Original seed topics ---
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
    # --- Platform-specific topics ---
    "capcut for pc download",
    "capcut for ios",
    "capcut online editor",
    "capcut web version",
    "capcut for mac",
    "capcut for chromebook",
    # --- Template & trend topics ---
    "capcut trending templates 2026",
    "capcut velocity template",
    "capcut slow motion template",
    "capcut photo editing template",
    "capcut aesthetic edit template",
    # --- AI feature topics ---
    "capcut ai remove background",
    "capcut ai upscale",
    "capcut text to speech",
    "capcut ai voice changer",
    "capcut ai image enhancer",
    # --- How-to tutorials ---
    "how to add music in capcut",
    "how to add subtitles in capcut",
    "how to speed up video in capcut",
    "how to use green screen in capcut",
    "how to make a slideshow in capcut",
    "how to resize video in capcut",
    "how to crop video in capcut",
    "how to add transitions in capcut",
    "how to use keyframes in capcut",
    "how to split video in capcut",
    "how to reverse video in capcut",
    "how to blur background in capcut",
    "how to stabilize video in capcut",
    "how to add voice over in capcut",
    "how to do slow motion in capcut",
    "how to remove audio in capcut",
    "how to merge videos in capcut",
    "how to add text in capcut",
    "how to zoom in capcut",
    "how to do speed ramp in capcut",
    # --- Fix / troubleshoot topics ---
    "capcut crashing fix",
    "capcut export failed fix",
    "capcut audio sync problem",
    "capcut video quality loss fix",
    "capcut app not opening fix",
    "capcut keeps freezing fix",
    # --- Download / APK topics ---
    "capcut mod apk latest version",
    "capcut apk for android",
    "capcut lite version",
    "capcut apk without watermark",
    # --- Alternatives topics ---
    "best capcut alternatives",
    "capcut alternatives for pc",
    "free video editors like capcut",
    "capcut alternatives in banned countries",
    # --- Update / changelog topics ---
    "capcut new update features",
    "capcut latest version changelog",
    "capcut new effects 2026",
    # --- Regional / ban topics ---
    "capcut banned countries list",
    "how to use capcut with vpn",
    "is capcut safe to use",
    # --- Comparison topics (new matchups) ---
    "capcut vs imovie",
    "capcut vs davinci resolve",
    "capcut vs powerdirector",
    "capcut vs vivavideo",
    "capcut vs splice",
    "capcut vs adobe express",
    "capcut vs picsart",
    "capcut vs lumafusion",
]

COMPARISON_TARGETS = [
    "Canva",
    "InShot",
    "VN",
    "KineMaster",
    "Alight Motion",
    "Premiere Rush",
    "Filmora",
    "iMovie",
    "DaVinci Resolve",
    "PowerDirector",
    "VivaVideo",
    "Splice",
    "Adobe Express",
    "Picsart",
    "LumaFusion",
]

COMPETITOR_SITEMAPS = [
    "https://capcutmodapk.id/sitemap_index.xml",
    "https://capcutapkpro.com/post-sitemap.xml",
    "https://capcutdownload.net/post-sitemap.xml",
    "https://modcombo.com/post-sitemap.xml",
    "https://apkdone.com/post-sitemap.xml",
]

# All content bucket types the pipeline recognises.
CONTENT_BUCKETS = [
    "comparison",
    "how_to",
    "fix",
    "trend",
    "safety",
    "download",
    "tutorial",
    "alternative",
    "platform",
    "update",
]

# Map each bucket to the primary schema types the article should carry.
ARTICLE_SCHEMA_TYPES = {
    "how_to":    ["Article", "HowTo", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "fix":       ["Article", "HowTo", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "tutorial":  ["Article", "HowTo", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "comparison":["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "download":  ["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "safety":    ["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "trend":     ["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "alternative":["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "platform":  ["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
    "update":    ["Article", "SoftwareApplication", "BreadcrumbList", "FAQPage"],
}

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
    "tutorial": 15,
    "alternative": 14,
    "platform": 12,
    "update": 10,
}
