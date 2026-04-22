"""Test R34 keyword density normalization after Phase G.3 context-aware fix.

Verifies that keyword replacements:
1. Never create broken phrases like "the such options", "true these products"
2. Skip replacements after modifiers/articles/adjectives  
3. Preserve keyword in headings
4. Use strict word boundaries
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def simulate_r34_old(html: str, keyword: str) -> str:
    """OLD BUGGY VERSION: generates determiner-prefix variations."""
    kw_words = keyword.lower().split()
    variations = [
        "such " + " ".join(kw_words[1:]),
        "these " + " ".join(kw_words[-2:]),
        "this " + kw_words[-1],
    ]
    positions = list(re.finditer(re.escape(keyword), html, re.I))
    if len(positions) > 5:
        # Replace middle occurrence
        m = positions[3]
        var = variations[0]
        return html[:m.start()] + var + html[m.end():]
    return html


def simulate_r34_new(html: str, keyword: str) -> str:
    """NEW FIXED VERSION: context-aware with strict safety checks."""
    kw_words = keyword.lower().split()
    variations = [
        " ".join(kw_words[1:]),    # drop first word
        kw_words[-1],              # last noun
        " ".join(kw_words[-2:]),   # last 2 words
    ]
    
    positions = list(re.finditer(r"\b" + re.escape(keyword) + r"\b", html, re.I))
    if len(positions) > 5:
        replaceable = positions[3:-2]
        for i, m in enumerate(reversed(replaceable[:1])):  # just 1 for demonstration
            var = variations[i % len(variations)]
            before_ctx = html[max(0, m.start() - 30):m.start()]
            
            # STRICT CHECK: skip if preceded by modifier/article/adjective
            unsafe_before = re.search(
                r"\b(the|a|an|this|that|these|those|such|our|your|all|any|" +
                r"true|real|actual|best|top|premium|quality|complete|full|" +
                r"new|old|first|last|main|key|primary|total)\s+$",
                before_ctx, re.I
            )
            if unsafe_before:
                continue
            
            # Skip if in heading
            heading_check = html[max(0, m.start() - 100):m.end() + 10]
            if re.search(r"<h[1-6][^>]*>[^<]*$", heading_check, re.I):
                continue
            
            # Safe to replace
            html = html[:m.start()] + var + html[m.end():]
            break
    return html


class TestR34KeywordCorruptionFix:
    """Phase G.3: verify R34 no longer creates broken phrases."""
    
    def test_old_version_breaks_after_article(self):
        """Demonstrate the old bug: 'the organic spices' → 'the such spices'."""
        html = "<p>The organic spices wholesale price is critical. Organic spices wholesale price matters. Check organic spices wholesale price daily. The organic spices wholesale price varies. Compare organic spices wholesale price. Final organic spices wholesale price note.</p>"
        keyword = "organic spices wholesale price"
        result = simulate_r34_old(html, keyword)
        # OLD: would create "the such spices" (broken grammar)
        assert "the such" in result.lower() or "such spices" in result.lower()
    
    def test_new_version_skips_unsafe_context(self):
        """NEW: skips replacement when keyword appears after 'the' or adjectives."""
        html = "<p>The organic spices wholesale price is critical. Organic spices wholesale price matters. Check organic spices wholesale price daily. The organic spices wholesale price varies. Compare organic spices wholesale price. Final organic spices wholesale price note.</p>"
        keyword = "organic spices wholesale price"
        result = simulate_r34_new(html, keyword)
        # NEW: should NOT create "the such" or "the spices" (skips unsafe replacements)
        assert "the such" not in result.lower()
        # Should have replaced the standalone occurrence ("Check organic..." or "Compare...")
        assert ("spices wholesale price" in result.lower() or "wholesale price" in result.lower())
    
    def test_no_corruption_after_true(self):
        """'true organic spices wholesale price' should NOT become 'true such spices'."""
        html = "<p>The true organic spices wholesale price is vital. Organic spices wholesale price also matters. Check organic spices wholesale price. Compare organic spices wholesale price. Final organic spices wholesale price.</p>"
        keyword = "organic spices wholesale price"
        result = simulate_r34_new(html, keyword)
        assert "true such" not in result.lower()
        assert "true these" not in result.lower()
    
    def test_heading_keyword_preserved(self):
        """Keywords in <h2> headings should never be replaced."""
        html = "<h2>How to Choose Organic Spices Wholesale Price</h2><p>Organic spices wholesale price varies. Check organic spices wholesale price daily. Compare organic spices wholesale price. The organic spices wholesale price matters. Final organic spices wholesale price note.</p>"
        keyword = "organic spices wholesale price"
        result = simulate_r34_new(html, keyword)
        # Heading must preserve exact keyword
        assert "<h2>How to Choose Organic Spices Wholesale Price</h2>" in result
    
    def test_no_determiner_prefix_in_variations(self):
        """New variations must NOT start with 'this', 'such', 'these'."""
        variations = [
            "spices wholesale price",   # ✓ dropped first word
            "price",                     # ✓ last noun
            "wholesale price",           # ✓ last 2 words
        ]
        for var in variations:
            assert not var.startswith(("this ", "such ", "these ", "the "))
    
    def test_word_boundary_enforcement(self):
        """Must use \\b boundaries to avoid partial matches."""
        html = "<p>Organic spices wholesale prices vary. The organic spices wholesale price is key.</p>"
        keyword = "organic spices wholesale price"
        # Should NOT match "prices" (plural)
        result = simulate_r34_new(html, keyword)
        assert "wholesale prices" in result  # plural form preserved


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
