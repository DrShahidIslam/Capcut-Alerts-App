from writer.article_generator import generate_article


def test_generate_article_adds_seo_fields_and_faq_schema():
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

    assert article["meta_title"]
    assert article["meta_description"]
    assert len(article["focus_keywords"]) >= 4
    assert article["faq_count"] >= 1
    assert "application/ld+json" in article["faq_schema"]
    assert '<a href="https://capcutpro-apks.com/' in article["content"]
