from detection.opportunity_detector import detect_opportunities


def test_detector_filters_existing_slug():
    existing_slugs = {"capcut-vs-canva"}
    bundles = [[{"query": "capcut vs canva", "source": "seed", "signals": ["comparison"], "freshness": 0.8}]]
    results = detect_opportunities(existing_slugs, bundles)
    assert results == []


def test_detector_scores_fix_queries_high_enough():
    existing_slugs = set()
    bundles = [[
        {"query": "capcut black screen fix", "source": "seed", "signals": ["core-topic"], "freshness": 0.8},
        {"query": "capcut black screen fix", "source": "google_suggest", "signals": ["autocomplete"], "freshness": 0.9},
    ]]
    results = detect_opportunities(existing_slugs, bundles)
    assert results
    assert results[0]["bucket"] == "fix"
    assert results[0]["score"] >= 35


def test_detector_limits_comparison_topic_dominance():
    existing_slugs = set()
    bundles = [[
        {"query": "capcut vs canva", "source": "seed", "signals": ["comparison"], "freshness": 0.9},
        {"query": "capcut vs inshot", "source": "seed", "signals": ["comparison"], "freshness": 0.9},
        {"query": "capcut vs vn editor", "source": "seed", "signals": ["comparison"], "freshness": 0.9},
        {"query": "capcut vs filmora", "source": "seed", "signals": ["comparison"], "freshness": 0.9},
        {"query": "capcut black screen fix", "source": "seed", "signals": ["core-topic"], "freshness": 0.9},
        {"query": "capcut export settings for tiktok", "source": "seed", "signals": ["core-topic"], "freshness": 0.8},
        {"query": "capcut templates trend", "source": "seed", "signals": ["rising"], "freshness": 0.8},
    ]]
    results = detect_opportunities(existing_slugs, bundles)
    comparison_count = sum(1 for item in results if item["bucket"] == "comparison")
    assert comparison_count < len(results)
    assert any(item["bucket"] == "fix" for item in results)
    assert any(item["bucket"] == "how_to" for item in results)
