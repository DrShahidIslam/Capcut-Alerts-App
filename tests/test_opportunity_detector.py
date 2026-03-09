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
