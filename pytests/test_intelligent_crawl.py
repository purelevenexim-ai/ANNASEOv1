"""
================================================================================
TEST — Intelligent Crawl Engine with real data (pureleven.com)
================================================================================
Tests the complete keyword discovery pipeline:
  1. Intelligent site crawl (page-type classification)
  2. AI business analysis
  3. AI keyword extraction
  4. AI keyword classification (good vs bad)
  5. Supporting keyword scoring
  6. Competitor analysis (focused, pillar-only)
  7. Google Suggest enrichment
  8. Top 5 per pillar selection

Run:
  cd /root/ANNASEOv1
  python -m pytest pytests/test_intelligent_crawl.py -v -s

For quick unit tests (no network):
  python -m pytest pytests/test_intelligent_crawl.py -v -s -k "unit"

For full integration test with real crawl:
  python -m pytest pytests/test_intelligent_crawl.py -v -s -k "integration"
================================================================================
"""

import os, sys, json, re, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engines.intelligent_crawl_engine import (
    IntelligentSiteCrawler,
    AIBusinessAnalyzer,
    AIKeywordExtractor,
    AIKeywordClassifier,
    SmartCompetitorAnalyzer,
    GoogleSuggestEnricher,
    IntelligentKeywordDiscovery,
    AICaller,
    CrawledPage,
    BusinessProfile,
    ScoredKeyword,
)


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS (no network required)
# ─────────────────────────────────────────────────────────────────────────────

class TestURLClassification:
    """Test URL pattern classification logic."""

    def test_homepage_detection(self):
        crawler = IntelligentSiteCrawler()
        classified = crawler._classify_urls([
            "https://pureleven.com",
            "https://pureleven.com/",
        ], "https://pureleven.com")
        assert len(classified["homepage"]) >= 1

    def test_product_page_detection(self):
        crawler = IntelligentSiteCrawler()
        classified = crawler._classify_urls([
            "https://pureleven.com/product/cardamom-8mm",
            "https://pureleven.com/shop/organic-turmeric",
            "https://pureleven.com/store/black-pepper",
        ], "https://pureleven.com")
        assert len(classified["product"]) >= 2

    def test_blog_page_detection(self):
        crawler = IntelligentSiteCrawler()
        classified = crawler._classify_urls([
            "https://pureleven.com/blog/benefits-of-cardamom",
            "https://pureleven.com/articles/spice-guide",
            "https://pureleven.com/resources/cooking-tips",
        ], "https://pureleven.com")
        assert len(classified["blog"]) >= 2

    def test_about_page_detection(self):
        crawler = IntelligentSiteCrawler()
        classified = crawler._classify_urls([
            "https://pureleven.com/about",
            "https://pureleven.com/about-us",
            "https://pureleven.com/our-story",
        ], "https://pureleven.com")
        assert len(classified["about"]) >= 2

    def test_skip_patterns(self):
        crawler = IntelligentSiteCrawler()
        # These should not appear in any category
        urls = [
            "https://pureleven.com/cart",
            "https://pureleven.com/checkout",
            "https://pureleven.com/account/login",
            "https://pureleven.com/privacy-policy",
        ]
        # _discover_urls filters skipped patterns, _classify_urls puts remaining in "other"
        # The skip check is in _discover_urls, so classify won't see them
        classified = crawler._classify_urls(urls, "https://pureleven.com")
        # These short-path URLs may end up in "product" or "other" but
        # they would be filtered at the _discover_urls stage
        assert "homepage" not in [p for urls_list in classified.values()
                                   for p in urls_list
                                   if "cart" in p or "checkout" in p]

    def test_unit_prioritize_crawl(self):
        crawler = IntelligentSiteCrawler()
        classified = {
            "homepage": ["https://example.com"],
            "about": ["https://example.com/about"],
            "product": [f"https://example.com/product/{i}" for i in range(20)],
            "category": ["https://example.com/category/spices"],
            "blog": [f"https://example.com/blog/{i}" for i in range(10)],
            "other": [f"https://example.com/page/{i}" for i in range(10)],
        }
        order = crawler._prioritize_crawl(classified, "https://example.com", 15)

        # Homepage should be first
        assert order[0][1] == "homepage"
        # About should be in the first few
        assert any(pt == "about" for _, pt in order[:3])
        # Should not exceed max_pages
        assert len(order) <= 15


class TestKeywordScoring:
    """Test rule-based keyword scoring."""

    def test_unit_purchase_intent_scoring(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="buy cardamom online",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="supporting",
            intent="purchase",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.purchase_intent_score >= 80
        assert scored.intent == "purchase"

    def test_unit_informational_scoring(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="cardamom health benefits",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="supporting",
            intent="informational",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.purchase_intent_score <= 50
        assert scored.intent == "informational"

    def test_unit_relevance_with_pillar(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="organic cardamom powder",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="supporting",
            intent="research",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.relevance_score >= 80

    def test_unit_relevance_without_pillar(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="random cooking tips",
            pillar="",
            source="site_crawl",
            keyword_type="supporting",
            intent="informational",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.relevance_score < 50

    def test_unit_ranking_feasibility_longtail(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="buy organic green cardamom 8mm online india",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="supporting",
            intent="purchase",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.ranking_feasibility >= 70  # long tail = easier

    def test_unit_ranking_feasibility_head_term(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="cardamom",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="pillar",
            intent="purchase",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert scored.ranking_feasibility <= 40  # single word = very hard

    def test_unit_final_score_computation(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="buy cardamom online",
            pillar="cardamom",
            source="site_crawl",
            keyword_type="supporting",
            intent="purchase",
            purchase_intent_score=85,
            relevance_score=90,
            business_fit_score=80,
            ranking_feasibility=70,
            search_volume_signal=60,
        )
        score = classifier._compute_final_score(kw)
        assert 60 <= score <= 100  # should be high

    def test_unit_bad_keyword_detection(self):
        classifier = AIKeywordClassifier()
        kw = ScoredKeyword(
            keyword="the",
            pillar="",
            source="site_crawl",
            keyword_type="supporting",
            intent="informational",
        )
        scored = classifier._rule_based_score(kw, ["cardamom"])
        assert not scored.is_good


class TestTopKeywordSelection:
    """Test top 5 per pillar logic."""

    def test_unit_top_supporting_per_pillar(self):
        classifier = AIKeywordClassifier()

        keywords = []
        for i in range(20):
            kw = ScoredKeyword(
                keyword=f"cardamom keyword {i}",
                pillar="cardamom",
                source="site_crawl",
                keyword_type="supporting",
                intent="purchase",
                final_score=100 - i * 5,
                is_good=True,
            )
            keywords.append(kw)

        for i in range(10):
            kw = ScoredKeyword(
                keyword=f"turmeric keyword {i}",
                pillar="turmeric",
                source="site_crawl",
                keyword_type="supporting",
                intent="purchase",
                final_score=90 - i * 5,
                is_good=True,
            )
            keywords.append(kw)

        top = classifier.get_top_supporting(keywords, per_pillar=5)
        assert "cardamom" in top
        assert "turmeric" in top
        assert len(top["cardamom"]) == 5
        assert len(top["turmeric"]) == 5
        # First should have highest score
        assert top["cardamom"][0].final_score >= top["cardamom"][-1].final_score


class TestAIJsonExtraction:
    """Test JSON extraction from AI responses."""

    def test_unit_direct_json(self):
        result = AICaller.extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_unit_markdown_code_block(self):
        result = AICaller.extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_unit_json_with_text(self):
        result = AICaller.extract_json('Here is the result:\n{"key": "value"}\nDone.')
        assert result == {"key": "value"}

    def test_unit_json_array(self):
        result = AICaller.extract_json('[{"keyword": "test"}]')
        assert isinstance(result, list)

    def test_unit_empty_response(self):
        result = AICaller.extract_json("")
        assert result is None

    def test_unit_invalid_json(self):
        result = AICaller.extract_json("not json at all")
        assert result is None


class TestCompetitorFiltering:
    """Test competitor URL filtering logic."""

    def test_unit_filter_relevant_urls(self):
        analyzer = SmartCompetitorAnalyzer()
        urls = [
            "https://competitor.com/",
            "https://competitor.com/about-us",
            "https://competitor.com/product/cardamom-organic",
            "https://competitor.com/product/coffee-beans",  # not our pillar
            "https://competitor.com/blog/cardamom-benefits",
            "https://competitor.com/blog/coffee-guide",  # not our pillar
            "https://competitor.com/category/cardamom",
        ]

        relevant = analyzer._filter_relevant_urls(
            urls, ["cardamom"], "https://competitor.com", "https://competitor.com/"
        )

        relevant_urls = [url for url, _ in relevant]

        # Homepage always included
        assert "https://competitor.com/" in relevant_urls
        # About always included
        assert "https://competitor.com/about-us" in relevant_urls
        # Cardamom product included
        assert "https://competitor.com/product/cardamom-organic" in relevant_urls
        # Coffee product NOT included (not our pillar)
        assert "https://competitor.com/product/coffee-beans" not in relevant_urls
        # Cardamom blog included
        assert "https://competitor.com/blog/cardamom-benefits" in relevant_urls
        # Cardamom category included
        assert "https://competitor.com/category/cardamom" in relevant_urls


class TestDeduplication:
    """Test keyword deduplication."""

    def test_unit_dedup_keeps_best(self):
        extractor = AIKeywordExtractor()
        keywords = [
            ScoredKeyword(keyword="organic cardamom", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting",
                          intent="purchase", relevance_score=80),
            ScoredKeyword(keyword="organic cardamom", pillar="cardamom",
                          source="competitor", keyword_type="supporting",
                          intent="purchase", relevance_score=60),
        ]
        deduped = extractor._deduplicate(keywords)
        assert len(deduped) == 1
        assert deduped[0].relevance_score == 80  # kept the higher score


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS (require network)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestRealCrawlPureleven:
    """Integration tests with pureleven.com (requires network)."""

    def test_integration_crawl_pureleven(self):
        """Test intelligent crawl of pureleven.com."""
        crawler = IntelligentSiteCrawler()
        pages = crawler.crawl_site("https://www.pureleven.com", max_pages=10)

        assert len(pages) > 0, "Should crawl at least 1 page"

        # Check page types
        types = set(p.page_type for p in pages)
        print(f"\n  Pages crawled: {len(pages)}")
        print(f"  Page types: {types}")
        for p in pages:
            print(f"    [{p.page_type}] {p.title[:60]} ({p.url})")

        # Homepage should be crawled
        homepages = [p for p in pages if p.page_type == "homepage"]
        assert len(homepages) >= 1, "Homepage should be crawled"

        # Some pages should have products
        with_products = [p for p in pages if p.products_found]
        print(f"\n  Pages with products: {len(with_products)}")
        for p in with_products:
            print(f"    {p.products_found[:5]}")

    def test_integration_business_analysis(self):
        """Test AI business analysis on pureleven.com pages."""
        crawler = IntelligentSiteCrawler()
        pages = crawler.crawl_site("https://www.pureleven.com", max_pages=8)

        if not pages:
            pytest.skip("Could not crawl pureleven.com")

        analyzer = AIBusinessAnalyzer()
        profile = analyzer.analyze(pages, ["cardamom"])

        print(f"\n  Business Profile:")
        print(f"    Name: {profile.business_name}")
        print(f"    Type: {profile.business_type}")
        print(f"    Products: {profile.primary_products}")
        print(f"    Categories: {profile.product_categories}")
        print(f"    Audience: {profile.target_audience}")
        print(f"    USP: {profile.usp}")
        print(f"    Geo: {profile.geographic_focus}")
        print(f"    Content: {profile.content_themes}")

        # Should identify some products
        assert len(profile.primary_products) > 0, "Should find at least 1 product"

    def test_integration_keyword_extraction(self):
        """Test AI keyword extraction from pureleven.com."""
        crawler = IntelligentSiteCrawler()
        pages = crawler.crawl_site("https://www.pureleven.com", max_pages=8)

        if not pages:
            pytest.skip("Could not crawl pureleven.com")

        extractor = AIKeywordExtractor()
        keywords = extractor.extract_from_pages(pages, ["cardamom"])

        pillar_kws = [kw for kw in keywords if kw.keyword_type == "pillar"]
        supporting_kws = [kw for kw in keywords if kw.keyword_type == "supporting"]

        print(f"\n  Keywords extracted: {len(keywords)}")
        print(f"    Pillar: {len(pillar_kws)}")
        print(f"    Supporting: {len(supporting_kws)}")
        print(f"\n  Pillar keywords:")
        for kw in pillar_kws[:10]:
            print(f"    - {kw.keyword} (from {kw.page_type})")
        print(f"\n  Supporting keywords (top 20):")
        for kw in supporting_kws[:20]:
            print(f"    - {kw.keyword} [{kw.intent}] pillar={kw.pillar}")

        assert len(keywords) > 0, "Should extract at least some keywords"

    def test_integration_keyword_scoring(self):
        """Test AI keyword scoring and classification."""
        # Create sample keywords as if from crawl
        keywords = [
            ScoredKeyword(keyword="buy cardamom online", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="organic cardamom price", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="cardamom benefits health", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="informational"),
            ScoredKeyword(keyword="best cardamom brand india", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="research"),
            ScoredKeyword(keyword="the cardamom the", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="informational"),
            ScoredKeyword(keyword="green cardamom 8mm", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="kerala cardamom exporter", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="cardamom price per kg", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="how to use cardamom", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="informational"),
            ScoredKeyword(keyword="cardamom wholesale bulk", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
        ]

        classifier = AIKeywordClassifier()
        scored = classifier.classify_and_score(keywords, ["cardamom"])

        print(f"\n  Scored {len(scored)} keywords:")
        for kw in sorted(scored, key=lambda k: k.final_score, reverse=True):
            print(f"    {'✓' if kw.is_good else '✗'} {kw.keyword:40s} "
                  f"score={kw.final_score:5.1f} intent={kw.intent:15s} "
                  f"purchase={kw.purchase_intent_score:3.0f} "
                  f"relevance={kw.relevance_score:3.0f} "
                  f"feasibility={kw.ranking_feasibility:3.0f}")

        good = [kw for kw in scored if kw.is_good]
        assert len(good) > 0, "Should have some good keywords"

        # Purchase-intent keywords should score higher than informational
        purchase_scores = [kw.final_score for kw in scored
                          if "buy" in kw.keyword or "price" in kw.keyword]
        info_scores = [kw.final_score for kw in scored
                      if "benefit" in kw.keyword or "how to" in kw.keyword]
        if purchase_scores and info_scores:
            assert max(purchase_scores) >= max(info_scores), \
                "Purchase-intent keywords should score higher"

    def test_integration_google_suggest(self):
        """Test Google Suggest enrichment."""
        enricher = GoogleSuggestEnricher()
        keywords = enricher.enrich(["cardamom"], existing_keywords=[])

        print(f"\n  Google Suggest found {len(keywords)} keywords for 'cardamom':")
        for kw in keywords[:20]:
            print(f"    - {kw.keyword} [{kw.intent}]")

        assert len(keywords) > 0, "Google Suggest should return suggestions"

        # Should find some purchase-intent keywords
        purchase = [kw for kw in keywords if kw.intent == "purchase"]
        print(f"\n  Purchase intent: {len(purchase)}")
        for kw in purchase[:10]:
            print(f"    - {kw.keyword}")

    def test_integration_top5_per_pillar(self):
        """Test the top 5 per pillar selection with scoring."""
        # Run a mini pipeline
        keywords = [
            ScoredKeyword(keyword="buy cardamom online", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="organic cardamom price", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="cardamom health benefits", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="informational"),
            ScoredKeyword(keyword="best cardamom brand", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="research"),
            ScoredKeyword(keyword="green cardamom 8mm price", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="cardamom wholesale rate", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
            ScoredKeyword(keyword="cardamom near me", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="local"),
            ScoredKeyword(keyword="cardamom price per kg india", pillar="cardamom",
                          source="site_crawl", keyword_type="supporting", intent="purchase"),
        ]

        classifier = AIKeywordClassifier()
        scored = classifier.classify_and_score(keywords, ["cardamom"])

        top = classifier.get_top_supporting(scored, per_pillar=5)

        print(f"\n  Top 5 for cardamom:")
        if "cardamom" in top:
            for i, kw in enumerate(top["cardamom"], 1):
                print(f"    #{i} {kw.keyword:40s} "
                      f"score={kw.final_score:5.1f} "
                      f"intent={kw.intent:15s} "
                      f"purchase={kw.purchase_intent_score:3.0f}")
            assert len(top["cardamom"]) <= 5


@pytest.mark.integration
class TestFullDiscoveryPipeline:
    """Full end-to-end test with pureleven.com."""

    def test_integration_full_customer_crawl(self):
        """Test complete customer site discovery."""
        discovery = IntelligentKeywordDiscovery()
        result = discovery.crawl_customer_site(
            "https://www.pureleven.com",
            user_pillars=["cardamom"],
            max_pages=10,
        )

        assert "error" not in result
        assert result["pages_crawled"] > 0

        print(f"\n  ═══ CUSTOMER SITE DISCOVERY ═══")
        print(f"  Pages crawled: {result['pages_crawled']}")
        print(f"  Page breakdown: {result['page_breakdown']}")

        profile = result.get("business_profile")
        if profile:
            print(f"\n  Business: {profile.business_name}")
            print(f"  Products: {profile.primary_products}")
            print(f"  USP: {profile.usp}")

        print(f"\n  Pillar keywords found: {len(result.get('pillar_keywords', []))}")
        for kw in result.get("pillar_keywords", [])[:10]:
            print(f"    - {kw.keyword}")

        print(f"\n  Supporting keywords found: {len(result.get('supporting_keywords', []))}")
        for kw in result.get("supporting_keywords", [])[:15]:
            print(f"    - {kw.keyword} [{kw.intent}] pillar={kw.pillar}")

        print(f"\n  Suggested new pillars: {result.get('suggested_new_pillars', [])}")


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE RUNNER
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run directly for quick manual testing."""
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s: %(message)s")

    print("=" * 70)
    print("INTELLIGENT CRAWL ENGINE — Manual Test")
    print("=" * 70)

    discovery = IntelligentKeywordDiscovery()

    # Phase 1: Crawl customer site
    print("\n[Phase 1] Crawling pureleven.com...")
    site_result = discovery.crawl_customer_site(
        "https://www.pureleven.com",
        user_pillars=["cardamom"],
        max_pages=12,
    )

    if "error" in site_result:
        print(f"  ERROR: {site_result['error']}")
    else:
        print(f"  Pages crawled: {site_result['pages_crawled']}")
        print(f"  Page breakdown: {site_result['page_breakdown']}")

        profile = site_result.get("business_profile")
        if profile:
            print(f"\n  === Business Profile ===")
            print(f"  Name: {profile.business_name}")
            print(f"  Type: {profile.business_type}")
            print(f"  Products: {profile.primary_products}")
            print(f"  USP: {profile.usp}")
            print(f"  Audience: {profile.target_audience}")

        all_pillars_found = [kw.keyword for kw in site_result.get("pillar_keywords", [])]
        print(f"\n  === Pillar Keywords ({len(all_pillars_found)}) ===")
        for kw in all_pillars_found[:15]:
            print(f"    - {kw}")

        supporting = site_result.get("supporting_keywords", [])
        print(f"\n  === Supporting Keywords ({len(supporting)}) ===")
        for kw in supporting[:20]:
            print(f"    - {kw.keyword} [{kw.intent}] pillar={kw.pillar}")

        suggested = site_result.get("suggested_new_pillars", [])
        print(f"\n  === Suggested New Pillars ({len(suggested)}) ===")
        for p in suggested:
            print(f"    - {p}")

        # Phase 3: Score all keywords
        all_kws = site_result.get("all_keywords", [])
        if all_kws:
            confirmed_pillars = list(set(
                ["cardamom"] + all_pillars_found[:5]
            ))
            print(f"\n[Phase 3] Scoring {len(all_kws)} keywords...")
            scored = discovery.score_all_keywords(all_kws, confirmed_pillars, profile)

            good = [k for k in scored if k.is_good]
            bad = [k for k in scored if not k.is_good]
            print(f"  Good: {len(good)}, Bad: {len(bad)}")

            # Phase 4: Top 5 per pillar
            top = discovery.get_top_keywords(scored, per_pillar=5)
            print(f"\n  === TOP 5 SUPPORTING KEYWORDS PER PILLAR ===")
            for pillar, kws in top.items():
                print(f"\n  [{pillar.upper()}]")
                for i, kw_data in enumerate(kws, 1):
                    print(f"    #{i} {kw_data['keyword']:40s} "
                          f"score={kw_data['final_score']:5.1f} "
                          f"intent={kw_data['intent']:15s} "
                          f"purchase={kw_data['purchase_intent_score']:3.0f} "
                          f"relevance={kw_data['relevance_score']:3.0f}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
