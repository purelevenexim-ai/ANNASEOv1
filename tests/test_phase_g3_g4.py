"""Phase G.3 + G.4 regression tests.

G.3: R19 sentence-opener variety must NOT splice mid-word. The original
implementation mutated `html` while iterating with stale match offsets,
producing artefacts like:
  - "lNotably, rmeric"     (was "love turmeric")
  - "enviWithout question" (was "environment")

G.4: h3s/themes/facts/entities lists may contain dicts (e.g. Mistral 7B
returns [{"text": "..."}] instead of ["..."]). The pipeline must coerce
gracefully without TypeError.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.content_generation_engine import SEOContentPipeline as ContentGenerationEngine  # noqa: E402


# ---------------------------------------------------------------------------
# G.4 — _coerce_str_list helper
# ---------------------------------------------------------------------------
class TestCoerceStrList:
    def test_pure_strings_pass_through(self):
        assert ContentGenerationEngine._coerce_str_list(["a", "b", "c"]) == ["a", "b", "c"]

    def test_mistral_dict_shape(self):
        items = [{"text": "First H3"}, {"text": "Second H3"}]
        assert ContentGenerationEngine._coerce_str_list(items) == ["First H3", "Second H3"]

    def test_mixed_str_and_dict(self):
        items = ["Plain", {"title": "From title"}, {"h3": "From h3 key"}]
        assert ContentGenerationEngine._coerce_str_list(items) == ["Plain", "From title", "From h3 key"]

    def test_empty_and_none_filtered(self):
        items = ["", None, {"text": ""}, "keep"]
        assert ContentGenerationEngine._coerce_str_list(items) == ["keep"]

    def test_handles_none_input(self):
        assert ContentGenerationEngine._coerce_str_list(None) == []

    def test_handles_empty_input(self):
        assert ContentGenerationEngine._coerce_str_list([]) == []

    def test_alt_dict_keys(self):
        items = [{"name": "Entity A"}, {"fact": "Fact B"}, {"value": "Val C"}, {"content": "Content D"}]
        assert ContentGenerationEngine._coerce_str_list(items) == ["Entity A", "Fact B", "Val C", "Content D"]

    def test_join_does_not_crash_on_dicts(self):
        """Original failure mode: ', '.join(items) where items contains dicts
        raised TypeError: sequence item 0: expected str instance, dict found."""
        items = [{"text": "One"}, {"text": "Two"}]
        # Should not raise:
        ", ".join(ContentGenerationEngine._coerce_str_list(items))

    def test_non_dict_non_str_coerced(self):
        items = [123, 4.5, "real"]
        assert ContentGenerationEngine._coerce_str_list(items) == ["123", "4.5", "real"]


# ---------------------------------------------------------------------------
# G.3 — R19 sentence-opener replacement must not splice mid-word
# ---------------------------------------------------------------------------
def _r19_replace(html: str) -> str:
    """Standalone reproduction of the R19 logic post-fix.

    Mirrors the production loop in `_apply_r19_humanization` so we can test
    the splice behaviour without instantiating the full engine.
    """
    ai_starter_replacements = {
        "this is ": ["Here, ", "Notice that ", "Consider how ", "Importantly, ", "You'll find "],
        "there are ": ["You'll find ", "Several ", "Multiple ", "A range of ", "Numerous "],
        "it is ": ["This proves ", "Clearly, ", "Without question, ", "Notably, ", "Evidently, "],
        "in this ": ["Throughout this ", "Across this ", "Within this ", "Here in this ", "Along this "],
    }
    for starter, replacements in ai_starter_replacements.items():
        pattern = re.compile(
            r'((?:^|[.!?]\s+|<p[^>]*>)\s*)(' + re.escape(starter) + r')',
            re.I | re.MULTILINE,
        )
        matches = list(pattern.finditer(html))
        if len(matches) > 3:
            targets = matches[2:7]
            for idx, m in enumerate(reversed(targets)):
                forward_idx = len(targets) - 1 - idx
                replacement = replacements[forward_idx % len(replacements)]
                if m.group(2)[0].isupper():
                    replacement = replacement[0].upper() + replacement[1:]
                html = html[:m.start(2)] + replacement + html[m.end(2):]
    return html


class TestR19NoMidWordSplice:
    def _build_html(self, starter: str, n_occurrences: int, tail: str) -> str:
        """Build paragraphs each starting with `starter`, plus a tail paragraph
        that contains words which previously got spliced (e.g. 'love turmeric').
        """
        paras = [f"<p>{starter}point {i} about something important.</p>" for i in range(n_occurrences)]
        paras.append(f"<p>{tail}</p>")
        return "\n".join(paras)

    def test_no_mid_word_splice_with_it_is(self):
        # 6 occurrences of "It is " forces R19 to fire and replace 4 of them.
        html = self._build_html("It is ", n_occurrences=6, tail="People love turmeric every day.")
        out = _r19_replace(html)
        # The tail must be untouched — no "lNotably," / "lWithout question," etc.
        assert "love turmeric" in out, f"Tail mid-word splice detected:\n{out}"
        assert "lNotably" not in out
        assert "lWithout" not in out
        assert "lClearly" not in out

    def test_no_mid_word_splice_with_in_this(self):
        html = self._build_html("In this ", n_occurrences=6, tail="The environment matters greatly today.")
        out = _r19_replace(html)
        assert "environment" in out, f"Tail mid-word splice detected:\n{out}"
        assert "enviThroughout" not in out
        assert "enviAcross" not in out

    def test_replacement_count_correct(self):
        html = self._build_html("It is ", n_occurrences=8, tail="Final paragraph here for context.")
        out = _r19_replace(html)
        # 8 occurrences → first 2 kept, next 5 replaced (cap), 1 remains untouched.
        remaining = len(re.findall(r"It is point", out))
        assert remaining == 3, f"Expected 3 remaining 'It is' (2 kept + 1 over cap); got {remaining}"

    def test_below_threshold_unchanged(self):
        html = self._build_html("It is ", n_occurrences=3, tail="Tail content.")
        out = _r19_replace(html)
        # Threshold is >3, so 3 occurrences must be untouched.
        assert out == html

    def test_html_length_grows_predictably(self):
        """No truncation or duplication should occur."""
        html = self._build_html("It is ", n_occurrences=6, tail="Here is a calm closing paragraph.")
        out = _r19_replace(html)
        # Output strictly longer (replacements are longer than "It is ").
        assert len(out) > len(html)
        # Closing paragraph preserved exactly.
        assert "Here is a calm closing paragraph." in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
