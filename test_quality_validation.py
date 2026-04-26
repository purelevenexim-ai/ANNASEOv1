#!/usr/bin/env python3
"""
Quick quality validation test for content generation fixes.
Tests integrity scan + forbidden phrase scrubbing + fake authority removal.
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_content_quality(keyword: str):
    """Generate one article and validate quality improvements."""
    print("\n" + "="*80)
    print(f"QUALITY VALIDATION TEST: {keyword}")
    print("="*80)
    
    try:
        from engines.content_generation_engine import SEOContentPipeline, AIRoutingConfig, StepAIConfig
        import uuid
        import sqlite3
        
        # Connect to DB
        db = sqlite3.connect("annaseo.db")
        db.row_factory = sqlite3.Row
        
        # Generate test article ID
        article_id = f"test_quality_{uuid.uuid4().hex[:8]}"
        
        # Look up existing spice project for realistic config
        proj = db.execute("SELECT * FROM projects WHERE project_id='proj_8ae940595b' LIMIT 1").fetchone()
        if not proj:
            print("⚠️  WARNING: Test project proj_8ae940595b not found, using defaults")
            project_name = "Test Spice Business"
            project_id = "proj_test_quality"
        else:
            project_name = dict(proj)["name"]
            project_id = "proj_8ae940595b"
        
        # Configure AI routing for OR Gemini Flash
        flash_chain = StepAIConfig("or_gemini_flash", "or_deepseek", "or_gemini_lite")
        routing = AIRoutingConfig(
            research=flash_chain,
            structure=flash_chain,
            verify=flash_chain,
            links=flash_chain,
            references=flash_chain,
            draft=flash_chain,
            recovery=flash_chain,
            review=flash_chain,
            issues=flash_chain,
            humanize=flash_chain,
            redevelop=flash_chain,
            score=flash_chain,
            quality_loop=flash_chain,
        )
        
        print(f"\nGenerating article for: {keyword}")
        print(f"AI Provider: or_gemini_flash (all steps)")
        print(f"Project: {project_name}")
        print("-" * 80)
        
        # Create pipeline
        pipeline = SEOContentPipeline(
            article_id=article_id,
            keyword=keyword,
            intent="commercial",
            project_name=project_name,
            title=f"Guide to {keyword.title()}",
            word_count=2000,
            project_id=project_id,
            db=db,
            supporting_keywords=[],
            product_links=[],
            target_audience="",
            content_type="blog",
            research_ai="auto",
            ai_routing=routing,
            page_type="article",
            page_inputs={},
            pipeline_mode="standard",  # Test the standard (full) pipeline where Step 6 was failing
        )
        
        # Enable multi-AI review (Claude + GPT via OpenRouter)
        pipeline.enable_multi_ai_review = False  # Disable for faster test focused on Step 6 fix
        
        # Load Ollama servers if any
        try:
            rows = db.execute("SELECT server_id, url, model FROM ollama_servers WHERE enabled=1").fetchall()
            pipeline._ollama_servers = {r["server_id"]: (r["url"], r["model"] or "") for r in rows}
        except Exception:
            pass
        
        # Run pipeline
        print("\n🚀 Starting content generation pipeline...")
        await pipeline.run()
        
        # Extract results from pipeline state
        state = pipeline.state
        html = state.final_html or ""
        word_count = state.word_count or 0
        quality_score = getattr(state, 'quality_score', 0)
        
        db.close()
        
        # Check for corruption patterns
        print("\n" + "="*80)
        print("INTEGRITY SCAN RESULTS")
        print("="*80)
        
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        
        # Check mid-word capital injections
        mid_word_caps = re.findall(r'\b([a-z]{1,3})\s+([A-Z][a-z]+)\s+([a-z]{2,})', text)
        if mid_word_caps:
            print(f"❌ FAILED: {len(mid_word_caps)} mid-word capital injection(s) detected:")
            for match in mid_word_caps[:3]:
                print(f"   - '{match[0]} {match[1]} {match[2]}'")
        else:
            print("✅ PASSED: No mid-word capital injections")
        
        # Check broken tokens
        broken_tokens = re.findall(r'\s(ges|hin|ect|tion|ing|ment|ness)\s+[a-z]', text)
        if broken_tokens:
            unique = list(set(broken_tokens))[:3]
            print(f"❌ FAILED: Broken token fragments detected: {', '.join(unique)}")
        else:
            print("✅ PASSED: No broken tokens")
        
        # Check for fake authority phrases
        print("\n" + "="*80)
        print("FAKE AUTHORITY CHECK")
        print("="*80)
        
        fake_authority_patterns = [
            r'\b(?:in our|after our|based on our) (?:testing|tests|evaluation)',
            r'\bwe (?:tested|evaluated|reviewed)',
            r'\bour team (?:tested|evaluated)',
            r'\bhands-on (?:testing|review)',
            r'\bafter putting .* to the test'
        ]
        
        found_fake_authority = False
        for pattern in fake_authority_patterns:
            matches = re.findall(pattern, text, re.I)
            if matches:
                print(f"❌ FAILED: Found fake authority phrase: {matches[0]}")
                found_fake_authority = True
        
        if not found_fake_authority:
            print("✅ PASSED: No fake authority phrases detected")
        
        # Check for templated fillers
        print("\n" + "="*80)
        print("TEMPLATED FILLER CHECK")
        print("="*80)
        
        filler_patterns = [
            r'\bthis (?:factor )?directly (?:influences|impacts|affects)',
            r'\bthis is especially relevant',
            r'\bwhat most (?:people|buyers) (?:miss|overlook)',
            r'\bexperienced buyers (?:check|look at)',
            r'\bin practice,?',
        ]
        
        found_fillers = False
        for pattern in filler_patterns:
            matches = re.findall(pattern, text, re.I)
            if matches:
                print(f"❌ FAILED: Found filler phrase: {matches[0]}")
                found_fillers = True
        
        if not found_fillers:
            print("✅ PASSED: No templated filler phrases")
        
        # Check for unsourced statistics
        print("\n" + "="*80)
        print("UNSOURCED STATISTICS CHECK")
        print("="*80)
        
        # Find all percentage claims
        all_percentages = re.findall(r'\d+%', text)
        # Find sourced percentages (with attribution within 50 chars)
        sourced_pattern = r'(?:According to|per|as per|based on|reports?|study|studies|research)[\w\s,()]{0,50}\d+%'
        sourced = re.findall(sourced_pattern, text, re.I)
        
        if all_percentages:
            print(f"Found {len(all_percentages)} percentage claim(s)")
            if len(sourced) >= len(all_percentages) * 0.8:  # 80% should be sourced
                print(f"✅ PASSED: {len(sourced)}/{len(all_percentages)} claims have attribution")
            else:
                print(f"⚠️  WARNING: Only {len(sourced)}/{len(all_percentages)} claims have attribution")
        else:
            print("ℹ️  No percentage claims in content")
        
        # Final summary
        print("\n" + "="*80)
        print("GENERATION SUMMARY")
        print("="*80)
        print(f"Keyword: {keyword}")
        print(f"Word Count: {word_count}")
        print(f"Quality Score: {quality_score}%")
        print(f"Title: {state.title if hasattr(state, 'title') else 'N/A'}")
        
        # Check editorial instructions for corruption warnings
        if hasattr(state, 'editorial_instructions') and state.editorial_instructions:
            corruption_instructions = [inst for inst in state.editorial_instructions if 'corruption' in inst.lower() or 'CRITICAL' in inst]
            if corruption_instructions:
                print("\n⚠️  EDITORIAL WARNINGS:")
                for inst in corruption_instructions:
                    print(f"  - {inst}")
        
        # Display multi-AI review results if available
        if hasattr(state, 'ai_reviews') and state.ai_reviews:
            print("\n" + "="*80)
            print("MULTI-AI REVIEW RESULTS")
            print("="*80)
            
            for ai_name, review in state.ai_reviews.items():
                if "error" in review:
                    print(f"\n{ai_name.upper()}: ❌ ERROR - {review['error']}")
                    continue
                
                if review.get("parse_error"):
                    print(f"\n{ai_name.upper()}: ⚠️  Parse error")
                    continue
                
                print(f"\n{ai_name.upper()} SCORES:")
                print(f"  Fake Authority: {review.get('fake_authority_score', 'N/A')}/10")
                print(f"  Filler Phrases: {review.get('filler_score', 'N/A')}/10")
                print(f"  Unsourced Stats: {review.get('unsourced_stats_score', 'N/A')}/10")
                print(f"  Text Corruption: {review.get('corruption_score', 'N/A')}/10")
                print(f"  Link Relevance: {review.get('link_relevance_score', 'N/A')}/10")
                print(f"  OVERALL QUALITY: {review.get('overall_quality_score', 'N/A')}/10")
                if review.get('top_improvement'):
                    print(f"  Top Fix: {review['top_improvement']}")
        
        # Save HTML for manual review
        output_file = Path(f"/tmp/quality_test_{keyword.replace(' ', '_')}.html")
        output_file.write_text(html)
        print(f"\n✅ Article saved to: {output_file}")
        
        # Print first 500 chars for quick inspection
        print("\n" + "="*80)
        print("CONTENT PREVIEW (first 500 chars)")
        print("="*80)
        print(text[:500] + "...")
        
        return {
            "html": html,
            "word_count": word_count,
            "quality_score": quality_score,
            "state": state
        }
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    """Run quality validation test."""
    keyword = "biriyani masala online"
    if len(sys.argv) > 1:
        keyword = " ".join(sys.argv[1:])
    
    result = await test_content_quality(keyword)
    
    if result:
        print("\n" + "="*80)
        print("✅ TEST COMPLETED SUCCESSFULLY")
        print("="*80)
        print("\nNext steps:")
        print("1. Review the saved HTML file for manual inspection")
        print("2. Check for link relevance and CTA quality")
        print("3. If clean, proceed with multi-AI review setup")
    else:
        print("\n" + "="*80)
        print("❌ TEST FAILED")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
