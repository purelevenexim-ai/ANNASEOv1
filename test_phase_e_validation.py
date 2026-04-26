#!/usr/bin/env python3
"""
Phase E Validation: Generate 5 articles across keyword types and score them.

Tests the complete pipeline (Phases A-D) against the quality gate: avg ≥ 88/100
across SEO, AEO, GEO, Humanization, Intelligence dimensions.
"""
import sys
import asyncio
import json
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

# Test keyword matrix: covers all 4 intent types + comparison variant
TEST_KEYWORDS = [
    {
        "keyword": "buy turmeric online kerala",
        "intent": "transactional",
        "expected_type": "buyer_guide",
        "label": "Transactional (buyer intent)",
    },
    {
        "keyword": "best spices for cooking",
        "intent": "commercial",
        "expected_type": "comparison_review",
        "label": "Commercial (comparison intent)",
    },
    {
        "keyword": "how to choose kitchen spices",
        "intent": "informational",
        "expected_type": "educational_guide",
        "label": "Informational (how-to)",
    },
    {
        "keyword": "alleppey vs erode turmeric",
        "intent": "commercial",
        "expected_type": "comparison_review",
        "label": "Comparison (A vs B)",
    },
    {
        "keyword": "organic black pepper benefits",
        "intent": "informational",
        "expected_type": "educational_guide",
        "label": "Informational (benefits)",
    },
]


def score_seo(html: str, keyword: str) -> int:
    """Quick SEO score (0-100): keyword in title/H1, meta, H2s, density."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    score = 0
    kw_lower = keyword.lower()
    
    # H1 contains keyword (20 pts)
    h1 = soup.find("h1")
    if h1 and kw_lower in h1.get_text().lower():
        score += 20
    
    # Multiple H2s (10 pts)
    h2s = soup.find_all("h2")
    if len(h2s) >= 5:
        score += 10
    
    # Keyword in at least one H2 (15 pts)
    if any(kw_lower in h2.get_text().lower() for h2 in h2s):
        score += 15
    
    # Word count 1500+ (20 pts)
    text = soup.get_text()
    word_count = len(text.split())
    if word_count >= 2000:
        score += 20
    elif word_count >= 1500:
        score += 15
    
    # Keyword density 1-2% (15 pts)
    kw_count = text.lower().count(kw_lower)
    density = (kw_count / word_count * 100) if word_count else 0
    if 1.0 <= density <= 2.0:
        score += 15
    elif 0.5 <= density <= 2.5:
        score += 10
    
    # Internal links (10 pts)
    links = soup.find_all("a", href=True)
    if len(links) >= 3:
        score += 10
    
    # FAQ section (10 pts)
    if any("faq" in h2.get("id", "").lower() for h2 in h2s):
        score += 10
    
    return min(score, 100)


def score_aeo(html: str) -> int:
    """Answer Engine Optimization: FAQ, lists, tables, structured content."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    score = 0
    
    # FAQ section exists (25 pts)
    h2s = soup.find_all("h2")
    if any("faq" in h2.get_text().lower() for h2 in h2s):
        score += 25
    
    # Lists (ul/ol) present (20 pts)
    lists = soup.find_all(["ul", "ol"])
    if len(lists) >= 3:
        score += 20
    elif len(lists) >= 1:
        score += 10
    
    # Table present (20 pts)
    if soup.find("table"):
        score += 20
    
    # Clear H2/H3 hierarchy (15 pts)
    h3s = soup.find_all("h3")
    if len(h2s) >= 4 and len(h3s) >= 4:
        score += 15
    
    # Short paragraphs avg (10 pts)
    paragraphs = soup.find_all("p")
    if paragraphs:
        avg_len = sum(len(p.get_text().split()) for p in paragraphs) / len(paragraphs)
        if avg_len <= 50:
            score += 10
    
    # Strong emphasis tags (10 pts)
    if len(soup.find_all("strong")) >= 5:
        score += 10
    
    return min(score, 100)


def score_geo(html: str, keyword: str) -> int:
    """Generative Engine Optimization: sources, authority, depth, uniqueness."""
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    score = 0
    
    # Citations/sources present (30 pts)
    citation_patterns = [
        r"according to \w+",
        r"\(20\d{2}\)",
        r"study found",
        r"research shows",
        r"fda|usda|iso|spices board",
    ]
    citations = sum(
        len(re.findall(pattern, text, re.IGNORECASE)) for pattern in citation_patterns
    )
    if citations >= 5:
        score += 30
    elif citations >= 3:
        score += 20
    
    # External links (15 pts)
    ext_links = [
        a for a in soup.find_all("a", href=True)
        if "http" in a["href"] and 'rel="noopener"' in str(a)
    ]
    if len(ext_links) >= 2:
        score += 15
    
    # Specific data points (20 pts)
    number_mentions = len(re.findall(r"\d+%|\d+\.\d+", text))
    if number_mentions >= 8:
        score += 20
    elif number_mentions >= 4:
        score += 10
    
    # Depth indicators (15 pts)
    depth_words = ["cultivar", "grade", "process", "threshold", "criterion", "variant"]
    depth_count = sum(text.lower().count(w) for w in depth_words)
    if depth_count >= 5:
        score += 15
    
    # Low forbidden-word density (20 pts)
    forbidden = [
        "delve", "landscape", "tapestry", "robust", "myriad",
        "in today's world", "let's explore"
    ]
    forbidden_count = sum(text.lower().count(w) for w in forbidden)
    if forbidden_count == 0:
        score += 20
    elif forbidden_count <= 2:
        score += 10
    
    return min(score, 100)


def score_humanization(html: str) -> int:
    """Human readability: questions, varied sentence starts, contractions, voice."""
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    score = 0
    
    # Questions present (20 pts)
    questions = text.count("?")
    if questions >= 5:
        score += 20
    elif questions >= 2:
        score += 10
    
    # Contractions (15 pts)
    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    if contractions >= 5:
        score += 15
    elif contractions >= 2:
        score += 10
    
    # Varied sentence starters (25 pts)
    sentences = re.split(r'[.!?]+', text)
    starters = [s.strip().split()[0] for s in sentences if len(s.strip().split()) > 0]
    unique_ratio = len(set(starters)) / len(starters) if starters else 0
    if unique_ratio >= 0.6:
        score += 25
    elif unique_ratio >= 0.4:
        score += 15
    
    # Personal pronouns minimal (15 pts)
    personal = text.lower().count(" we ") + text.lower().count(" our ")
    if personal <= 2:
        score += 15
    elif personal <= 5:
        score += 10
    
    # Active voice indicators (15 pts)
    active_patterns = [r"\b(do|does|did|make|build|create|choose)\b"]
    active_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in active_patterns)
    if active_count >= 10:
        score += 15
    
    # Short avg sentence (10 pts)
    if sentences:
        avg_sentence_len = len(text.split()) / len(sentences)
        if avg_sentence_len <= 20:
            score += 10
    
    return min(score, 100)


def score_intelligence(html: str, keyword: str) -> int:
    """Editorial intelligence: angle consistency, buyer guidance, concrete examples."""
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    score = 0
    
    # "How to choose" guidance (25 pts)
    guidance_patterns = [
        r"how to (choose|select|identify|buy)",
        r"what to look for",
        r"key (criteria|factors|considerations)",
        r"best for",
        r"recommended for",
    ]
    guidance = sum(len(re.findall(p, text, re.IGNORECASE)) for p in guidance_patterns)
    if guidance >= 4:
        score += 25
    elif guidance >= 2:
        score += 15
    
    # Concrete examples (20 pts)
    example_patterns = [r"for example", r"in practice", r"such as", r"e\.g\."]
    examples = sum(len(re.findall(p, text, re.IGNORECASE)) for p in example_patterns)
    if examples >= 3:
        score += 20
    elif examples >= 1:
        score += 10
    
    # Comparison structure (15 pts)
    comparison_words = ["vs", "versus", "compared to", "difference between", "pros and cons"]
    comp_count = sum(text.lower().count(w) for w in comparison_words)
    if comp_count >= 2:
        score += 15
    
    # CTA present (15 pts)
    cta_patterns = [
        r"shop now", r"buy now", r"learn more", r"explore",
        r"check out", r"discover", r"find out"
    ]
    ctas = sum(len(re.findall(p, text, re.IGNORECASE)) for p in cta_patterns)
    if ctas >= 2:
        score += 15
    elif ctas >= 1:
        score += 10
    
    # Specific product/variety names (15 pts)
    # Check for capitalized proper nouns (varieties, brands, locations)
    proper_nouns = len(re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", text))
    if proper_nouns >= 10:
        score += 15
    
    # No generic openers (10 pts)
    generic_openers = [
        "are you looking to",
        "in today's world",
        "let us explore",
        "without further ado"
    ]
    generic_count = sum(text.lower().count(opener) for opener in generic_openers)
    if generic_count == 0:
        score += 10
    
    return min(score, 100)


def calculate_scores(html: str, keyword: str) -> Dict[str, int]:
    """Calculate all 5 dimension scores."""
    return {
        "seo": score_seo(html, keyword),
        "aeo": score_aeo(html),
        "geo": score_geo(html, keyword),
        "humanization": score_humanization(html),
        "intelligence": score_intelligence(html, keyword),
    }


async def generate_article(keyword: str, intent: str, project_id: str = "proj_test_phase_e"):
    """Generate a single article using the full pipeline."""
    from engines.content_generation_engine import SEOContentPipeline
    import uuid
    
    article_id = f"test_phase_e_{uuid.uuid4().hex[:8]}"
    
    # Use lean mode for faster generation
    pipeline = SEOContentPipeline(
        article_id=article_id,
        keyword=keyword,
        project_id=project_id,
        page_type="blog",
        intent=intent,
        word_count=2000,
        pipeline_mode="lean",  # Lean mode = single draft pass
    )
    
    print(f"\n{'─'*70}")
    print(f"🔄 Generating: {keyword} ({intent})")
    print(f"{'─'*70}")
    
    try:
        await pipeline.run()
        
        html = pipeline.state.final_html or ""
        if html:
            intent_plan = pipeline._intent_data.get("plan", {})
            
            print(f"✅ Generated {len(html)} chars")
            print(f"   Intent plan: {intent_plan.get('article_type', 'N/A')}")
            print(f"   Angle: {intent_plan.get('angle', 'N/A')[:80]}...")
            
            return {
                "keyword": keyword,
                "intent": intent,
                "html": html,
                "intent_plan": intent_plan,
                "word_count": len(html.split()),
            }
        else:
            print(f"❌ Generation failed: no final_html generated")
            return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run full validation suite."""
    print("\n" + "="*70)
    print("PHASE E VALIDATION: 5-Article Quality Test")
    print("="*70)
    print(f"\nTest matrix: {len(TEST_KEYWORDS)} keywords across 4 intent types")
    print("\nQuality gate: avg ≥ 88/100 across all 5 dimensions\n")
    
    results = []
    
    # Generate each article
    for i, test_case in enumerate(TEST_KEYWORDS, 1):
        print(f"\n[{i}/{len(TEST_KEYWORDS)}] {test_case['label']}")
        
        article = await generate_article(
            keyword=test_case["keyword"],
            intent=test_case["intent"],
        )
        
        if not article:
            print(f"⚠️  Skipping {test_case['keyword']} — generation failed")
            continue
        
        # Score the article
        scores = calculate_scores(article["html"], test_case["keyword"])
        avg_score = sum(scores.values()) / len(scores)
        
        print(f"\n📊 Scores:")
        print(f"   SEO:           {scores['seo']:>3}/100")
        print(f"   AEO:           {scores['aeo']:>3}/100")
        print(f"   GEO:           {scores['geo']:>3}/100")
        print(f"   Humanization:  {scores['humanization']:>3}/100")
        print(f"   Intelligence:  {scores['intelligence']:>3}/100")
        print(f"   ─────────────────────")
        print(f"   AVERAGE:       {avg_score:>3.1f}/100")
        
        results.append({
            "keyword": test_case["keyword"],
            "label": test_case["label"],
            "scores": scores,
            "avg": avg_score,
            "word_count": article["word_count"],
            "article_type": article["intent_plan"].get("article_type", "N/A"),
        })
    
    # Final summary
    print("\n\n" + "="*70)
    print("FINAL RESULTS")
    print("="*70)
    
    if not results:
        print("❌ No articles generated successfully")
        return
    
    # Calculate aggregate stats
    all_seo = [r["scores"]["seo"] for r in results]
    all_aeo = [r["scores"]["aeo"] for r in results]
    all_geo = [r["scores"]["geo"] for r in results]
    all_human = [r["scores"]["humanization"] for r in results]
    all_intel = [r["scores"]["intelligence"] for r in results]
    all_avg = [r["avg"] for r in results]
    
    print(f"\nPer-dimension averages (n={len(results)}):")
    print(f"  SEO:           {sum(all_seo)/len(all_seo):.1f}/100")
    print(f"  AEO:           {sum(all_aeo)/len(all_aeo):.1f}/100")
    print(f"  GEO:           {sum(all_geo)/len(all_geo):.1f}/100")
    print(f"  Humanization:  {sum(all_human)/len(all_human):.1f}/100")
    print(f"  Intelligence:  {sum(all_intel)/len(all_intel):.1f}/100")
    
    overall_avg = sum(all_avg) / len(all_avg)
    print(f"\n{'─'*70}")
    print(f"OVERALL AVERAGE: {overall_avg:.1f}/100")
    print(f"{'─'*70}")
    
    # Quality gate decision
    if overall_avg >= 88.0:
        print("\n✅ QUALITY GATE: PASSED")
        print("   All 4 phases (A-D) successfully lifted quality above 88/100.")
        print("   Recommendation: STOP — no need for Tier 3 multi-model competition.")
    elif overall_avg >= 82.0:
        print("\n⚠️  QUALITY GATE: BORDERLINE")
        print(f"   Score {overall_avg:.1f}/100 is above baseline but below target.")
        print("   Recommendation: Review weak dimensions and consider Tier 3A.")
    else:
        print("\n❌ QUALITY GATE: FAILED")
        print(f"   Score {overall_avg:.1f}/100 is below target.")
        print("   Recommendation: Proceed to Tier 3A (multi-model intro competition).")
    
    # Save detailed results
    output_file = Path(__file__).parent / "test-results" / "phase_e_validation.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with output_file.open("w") as f:
        json.dump({
            "timestamp": "2026-04-21",
            "test_count": len(results),
            "results": results,
            "averages": {
                "seo": sum(all_seo)/len(all_seo),
                "aeo": sum(all_aeo)/len(all_aeo),
                "geo": sum(all_geo)/len(all_geo),
                "humanization": sum(all_human)/len(all_human),
                "intelligence": sum(all_intel)/len(all_intel),
                "overall": overall_avg,
            },
            "quality_gate_passed": overall_avg >= 88.0,
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
