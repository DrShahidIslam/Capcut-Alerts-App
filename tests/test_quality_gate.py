from writer.quality_gate import validate_article_for_publish


def test_quality_gate_blocks_fallback_trend_with_weak_sources():
    article = {
        "title": "CapCut Velocity Template Trend: Trending Now + How to Use It [2026]",
        "bucket": "trend",
        "is_fallback": True,
        "content": "<p>CapCut trend filler.</p><h2>Why this trend works</h2><p>Boost your views.</p>",
        "meta_title": "CapCut Velocity Template Trend",
        "meta_description": "Learn the CapCut velocity template trend with quick tips and a practical guide for creators today.",
        "faq_count": 1,
        "source_quality": {
            "source_count": 0,
            "unique_domain_count": 0,
            "official_count": 0,
        },
        "editorial_flags": [],
        "needs_manual_fact_check": True,
    }

    result = validate_article_for_publish(article, min_words=20)

    assert not result["ok"]
    assert any("template fallback only" in issue.lower() for issue in result["issues"])
    assert any("require at least 2 sources" in issue.lower() for issue in result["issues"])
