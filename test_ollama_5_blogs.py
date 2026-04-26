#!/usr/bin/env python3
"""
Phase F.3 — Ollama-only 5-article validation.

Tests the complete pipeline (Phases A-F) using ONLY Ollama (mistral:7b)
across 5 keyword types. Goal: prove the engine produces clean drafts
without expensive Gemini/OpenRouter calls, AND surface any
generation-time issues that need a different architectural approach.
"""
import sys, asyncio, json, re, uuid, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engines.content_generation_engine import (
    SEOContentPipeline, AIRoutingConfig, StepAIConfig
)
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

TEST_KEYWORDS = [
    {"keyword": "buy turmeric online kerala",      "intent": "transactional",  "label": "Transactional"},
    {"keyword": "best spices for cooking",          "intent": "commercial",     "label": "Commercial"},
    {"keyword": "how to choose kitchen spices",     "intent": "informational",  "label": "Informational (how-to)"},
    {"keyword": "alleppey vs erode turmeric",       "intent": "commercial",     "label": "Comparison"},
    {"keyword": "organic black pepper benefits",    "intent": "informational",  "label": "Informational (benefits)"},
]


def ollama_only_routing() -> AIRoutingConfig:
    """Force every pipeline step to use Ollama as primary, with skip fallback."""
    cfg = StepAIConfig("ollama", "skip", "skip")
    return AIRoutingConfig(
        research=cfg, structure=cfg, verify=cfg, links=cfg, references=cfg,
        draft=cfg, recovery=cfg, review=cfg, issues=cfg, humanize=cfg, redevelop=cfg,
    )


def diagnose(html: str, keyword: str) -> dict:
    """Run diagnostic checks for the issues Phase F is supposed to fix."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    h2s = [h.get_text().strip() for h in soup.find_all("h2")]
    words = len(text.split())

    # Fake authority phrases
    fake_phrases = [
        "we've observed", "we've found", "we've discovered", "we've seen",
        "we advise", "we ship", "we ensure", "we tested", "we observed",
        "we believe", "we noticed", "in our experience", "our team",
        "in our kitchen", "after putting"
    ]
    fake_hits = sum(text.lower().count(p) for p in fake_phrases)

    # Commercial URLs / orphaned CTAs
    urls = len(re.findall(r"\b[a-z0-9-]+\.com[/\w\-]*", text, re.IGNORECASE))

    # Definition repetitions
    def_pat = re.compile(rf"\b{re.escape(keyword)}\s+(?:refers to|is\s+(?:a|an|the)|means|describes)\b", re.IGNORECASE)
    def_count = len(def_pat.findall(text))

    # Duplicate H2s
    dup_h2 = 0
    for i, h1 in enumerate(h2s):
        for h2 in h2s[i+1:]:
            if SequenceMatcher(None, h1.lower(), h2.lower()).ratio() >= 0.7:
                dup_h2 += 1

    # Incomplete sentences
    paras = [p.get_text().strip() for p in soup.find_all("p")]
    incomplete = sum(
        1 for p in paras
        if re.search(r"(?:accounting for|based on|leading to|such as|including|ranging from)\s*$", p, re.IGNORECASE)
    )

    # Text corruption (mid-word splices)
    corruption = len(re.findall(r"\b\w+(?:sct|wsct|esct|rsct)\b", text, re.IGNORECASE))

    # Keyword density
    kw_count = text.lower().count(keyword.lower())
    density = (kw_count / words * 100) if words else 0

    # Section structure quality
    h3s = len(soup.find_all("h3"))
    lists = len(soup.find_all(["ul", "ol"]))
    tables = len(soup.find_all("table"))
    has_faq = any("faq" in h.lower() or "frequently asked" in h.lower() for h in h2s)

    return {
        "words": words,
        "h2_count": len(h2s),
        "h3_count": h3s,
        "lists": lists,
        "tables": tables,
        "has_faq": has_faq,
        "kw_density": round(density, 2),
        "fake_authority": fake_hits,
        "urls": urls,
        "def_repetitions": def_count,
        "duplicate_h2_pairs": dup_h2,
        "incomplete_sentences": incomplete,
        "text_corruption": corruption,
    }


def quality_score(diag: dict) -> int:
    """Score 0-100 based on issue detection + structural completeness."""
    score = 100
    # Critical issues (-15 each)
    score -= diag["fake_authority"] * 15
    score -= diag["duplicate_h2_pairs"] * 15
    score -= diag["urls"] * 5
    score -= max(0, diag["def_repetitions"] - 1) * 10
    score -= diag["incomplete_sentences"] * 10
    score -= diag["text_corruption"] * 8
    # Structural minimums
    if diag["h2_count"] < 5: score -= 10
    if diag["lists"] < 2: score -= 5
    if not diag["has_faq"]: score -= 10
    if diag["words"] < 1500: score -= 15
    if not (1.0 <= diag["kw_density"] <= 2.5): score -= 10
    return max(0, min(100, score))


async def generate(keyword: str, intent: str) -> dict:
    aid = f"ollama_{uuid.uuid4().hex[:8]}"
    pipeline = SEOContentPipeline(
        article_id=aid,
        keyword=keyword,
        project_id="proj_ollama_test",
        page_type="blog",
        intent=intent,
        word_count=2000,
        pipeline_mode="lean",
        ai_routing=ollama_only_routing(),
    )
    t0 = time.time()
    try:
        await pipeline.run()
        elapsed = time.time() - t0
        html = pipeline.state.final_html or ""
        return {"html": html, "elapsed_sec": round(elapsed, 1), "error": None}
    except Exception as e:
        return {"html": "", "elapsed_sec": round(time.time() - t0, 1), "error": str(e)}


async def main():
    print("\n" + "=" * 70)
    print("PHASE F.3 — OLLAMA-ONLY 5-ARTICLE VALIDATION")
    print("=" * 70)
    print(f"Routing: ALL steps → mistral:7b-instruct-q4_K_M (remote)")
    print(f"Pipeline: lean | Word target: 2000\n")

    results = []
    for i, tc in enumerate(TEST_KEYWORDS, 1):
        print(f"\n[{i}/{len(TEST_KEYWORDS)}] {tc['label']} — '{tc['keyword']}'")
        print("─" * 70)
        out = await generate(tc["keyword"], tc["intent"])

        if out["error"] or not out["html"]:
            print(f"  ❌ FAILED: {out['error'] or 'empty html'} ({out['elapsed_sec']}s)")
            results.append({**tc, "error": out["error"], "elapsed_sec": out["elapsed_sec"]})
            continue

        diag = diagnose(out["html"], tc["keyword"])
        score = quality_score(diag)
        print(f"  ✓ {out['elapsed_sec']}s | {diag['words']}w | {diag['h2_count']} H2s | density {diag['kw_density']}%")
        print(f"  Issues: fake-auth={diag['fake_authority']}  dup-H2={diag['duplicate_h2_pairs']}  "
              f"urls={diag['urls']}  def-repeat={diag['def_repetitions']}  "
              f"incomplete={diag['incomplete_sentences']}  corrupt={diag['text_corruption']}")
        print(f"  SCORE: {score}/100")

        # Save artifact
        out_dir = Path(__file__).parent / "test-results" / "ollama_5"
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", tc["keyword"].lower()).strip("_")
        (out_dir / f"{slug}.html").write_text(out["html"])

        results.append({**tc, "diagnostics": diag, "score": score, "elapsed_sec": out["elapsed_sec"]})

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    successful = [r for r in results if "score" in r]
    if successful:
        avg = sum(r["score"] for r in successful) / len(successful)
        avg_time = sum(r["elapsed_sec"] for r in successful) / len(successful)
        print(f"\n  Articles generated: {len(successful)}/{len(results)}")
        print(f"  Average score:      {avg:.1f}/100")
        print(f"  Average time/article: {avg_time:.1f}s")
        print(f"\n  Per-article scores:")
        for r in successful:
            print(f"    {r['score']:3d}/100  {r['elapsed_sec']:6.1f}s  {r['keyword']}")

        # Aggregate issue counts
        agg = {}
        for r in successful:
            for k, v in r["diagnostics"].items():
                if isinstance(v, (int, float)):
                    agg[k] = agg.get(k, 0) + v
        print(f"\n  Aggregate issues across all articles:")
        for k in ("fake_authority", "duplicate_h2_pairs", "urls", "def_repetitions",
                  "incomplete_sentences", "text_corruption"):
            print(f"    {k:25s}: {agg.get(k, 0)}")

    # Save full report
    out_file = Path(__file__).parent / "test-results" / "ollama_5_validation.json"
    out_file.write_text(json.dumps({"results": results}, indent=2, default=str))
    print(f"\n📄 Saved: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
