#!/usr/bin/env python3
"""Quick status checker for Kerala spices article generation."""
import sqlite3

article_id = 'art_cd023220a0'

conn = sqlite3.connect('annaseo.db')
row = conn.execute("""
    SELECT status, seo_score, review_score, eeat_score, geo_score, 
           word_count, error_message, updated_at
    FROM content_articles WHERE article_id=?
""", (article_id,)).fetchone()
conn.close()

if not row:
    print("❌ Article not found")
    exit(1)

status, seo, review, eeat, geo, wc, err, updated = row

print("="*70)
print(f"📊 ARTICLE STATUS: {status.upper()}")
print("="*70)
print(f"Keyword: Fresh vs Dried Kerala Spices")
print(f"Model: Ollama qwen2.5:3b (FREE)")
print(f"Last Updated: {updated}")
print()

if status == 'generating':
    print("⏳ Still generating... (this takes 5-10 minutes)")
    print("   Run this script again to check progress")
    
elif status == 'draft':
    print("✅ GENERATION COMPLETE!\n")
    print("📊 QUALITY SCORES:")
    if seo: print(f"   SEO Score:    {seo:.1f}%")
    if review: print(f"   Review Score: {review:.1f}%")
    if eeat: print(f"   E-E-A-T:      {eeat:.1f}%")
    if geo: print(f"   GEO Score:    {geo:.1f}%")
    print(f"   Word Count:   {wc}")
    
    scores = [s for s in [seo, review, eeat, geo] if s]
    if scores:
        avg = sum(scores) / len(scores)
        print(f"\n   📈 AVERAGE QUALITY: {avg:.1f}%")
        
        if avg >= 90:
            print(f"   🎉 EXCELLENT - TARGET ACHIEVED! (9/10+)")
        elif avg >= 85:
            print(f"   ✅ GOOD - HIGH QUALITY (8.5/10)")
        elif avg >= 80:
            print(f"   ⚠️  ACCEPTABLE (8/10)")
        else:
            print(f"   ❌ BELOW TARGET ({avg/10:.1f}/10)")
    
    print(f"\n   View in UI: http://localhost:8000")
    
elif status == 'failed':
    print(f"❌ GENERATION FAILED")
    print(f"   Error: {err}")
    print(f"\n   Try again or check worker logs")
    
else:
    print(f"Status: {status}")
    if wc:
        print(f"Words: {wc}")

print("="*70)
