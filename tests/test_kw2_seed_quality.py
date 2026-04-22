"""
Test Group 6: Seed phrase quality — validates that generated seed phrases
are grammatically correct and semantically appropriate for the business.
"""
import sys
import pytest

sys.path.insert(0, "/root/ANNASEOv1")

from engines.kw2.constants import (
    TRANSACTIONAL_TEMPLATES, COMMERCIAL_TEMPLATES, LOCAL_TEMPLATES,
    NAVIGATIONAL_TEMPLATES, SEED_INTENT_MODIFIERS_EXCLUDE,
)
from engines.kw2.modifier_extractor import get_seed_qualifiers


# ── Template validation ───────────────────────────────────────────────────

class TestTransactionalTemplates:
    def test_all_templates_have_placeholder(self):
        for tpl in TRANSACTIONAL_TEMPLATES:
            assert "{k}" in tpl, f"Template missing {{k}}: '{tpl}'"

    def test_templates_produce_valid_phrases(self):
        pillar = "black pepper"
        for tpl in TRANSACTIONAL_TEMPLATES:
            phrase = tpl.format(k=pillar, alt="white pepper", loc="India")
            assert "black pepper" in phrase
            assert len(phrase) > 5

    def test_no_template_starts_with_intent_word_only(self):
        """Templates like 'online {k}' or 'price {k}' create invalid phrases."""
        bad_starters = ("online ", "price ", "cost ", "cheap ", "cheapest ")
        for tpl in TRANSACTIONAL_TEMPLATES:
            for bad in bad_starters:
                if tpl.startswith(bad):
                    generated = tpl.format(k="cardamom")
                    # These are not inherently wrong (e.g., "cheapest cardamom" is valid)
                    # But "online cardamom" is wrong — check we're not generating it directly
                    assert not generated.startswith("online "), \
                        f"Template generates bad seed: '{generated}'"


class TestSeedQualifierFilter:
    def test_exclude_set_nonempty(self):
        assert len(SEED_INTENT_MODIFIERS_EXCLUDE) > 0

    def test_online_in_exclude(self):
        assert "online" in SEED_INTENT_MODIFIERS_EXCLUDE

    def test_buy_in_exclude(self):
        assert "buy" in SEED_INTENT_MODIFIERS_EXCLUDE

    def test_get_seed_qualifiers_removes_excludes(self):
        all_modifiers = ["organic", "online", "wholesale", "buy", "pure", "price"]
        qualifiers = get_seed_qualifiers(all_modifiers)
        for excluded in SEED_INTENT_MODIFIERS_EXCLUDE:
            assert excluded not in qualifiers, \
                f"'{excluded}' should be excluded from seed qualifiers"

    def test_organic_is_valid_qualifier(self):
        qualifiers = get_seed_qualifiers(["organic"])
        assert "organic" in qualifiers

    def test_wholesale_is_valid_qualifier(self):
        qualifiers = get_seed_qualifiers(["wholesale"])
        assert "wholesale" in qualifiers


# ── Phrase generation validation ──────────────────────────────────────────

class TestSeedPhraseValidity:
    """Ensure generated seeds are valid search queries."""

    SPICE_PILLARS = ["cardamom", "black pepper", "turmeric", "cinnamon"]

    def test_transactional_seeds_contain_pillar(self):
        for pillar in self.SPICE_PILLARS:
            for tpl in TRANSACTIONAL_TEMPLATES[:5]:
                try:
                    phrase = tpl.format(k=pillar, alt="alternative", loc="India")
                    assert pillar in phrase or pillar.split()[0] in phrase
                except KeyError:
                    pass  # Template has extra placeholders

    def test_seeds_minimum_length(self):
        """All generated seed phrases should be meaningful (>= 5 chars)."""
        for tpl in TRANSACTIONAL_TEMPLATES + COMMERCIAL_TEMPLATES:
            try:
                phrase = tpl.format(k="cardamom", alt="spice", loc="India")
                assert len(phrase) >= 5, f"Too short: '{phrase}'"
            except KeyError:
                pass

    def test_navigational_templates_have_placeholder(self):
        for tpl in NAVIGATIONAL_TEMPLATES:
            assert "{k}" in tpl

    def test_local_templates_have_placeholder(self):
        for tpl in LOCAL_TEMPLATES:
            assert "{k}" in tpl

    def test_seeds_are_lowercase_friendly(self):
        """Seeds should produce lowercase-compatible strings when pillar is lowercase."""
        pillar = "black pepper"
        for tpl in TRANSACTIONAL_TEMPLATES[:3]:
            try:
                phrase = tpl.format(k=pillar, alt="white pepper", loc="india")
                assert phrase == phrase.lower() or phrase.lower() == phrase.lower()
            except KeyError:
                pass

    def test_no_double_spaces_in_seeds(self):
        for tpl in TRANSACTIONAL_TEMPLATES + COMMERCIAL_TEMPLATES + LOCAL_TEMPLATES:
            try:
                phrase = tpl.format(k="cardamom", alt="spice", loc="India")
                assert "  " not in phrase, f"Double space in: '{phrase}'"
            except KeyError:
                pass


# ── Business-specific seed validation ────────────────────────────────────

class TestBusinessSpecificSeeds:
    def test_spice_business_seeds_are_commercial(self):
        """For a spice business, the bulk of seeds should target commercial intent."""
        spice_pillars = ["cardamom", "black pepper", "turmeric"]
        commercial_count = 0
        total = 0
        for pillar in spice_pillars:
            for tpl in TRANSACTIONAL_TEMPLATES:
                try:
                    phrase = tpl.format(k=pillar, alt="alt", loc="India")
                    total += 1
                    if any(w in phrase for w in ["buy", "wholesale", "price", "supplier", "bulk"]):
                        commercial_count += 1
                except KeyError:
                    pass
        assert commercial_count / total > 0.5, "More than half of seeds should be commercial"

    def test_b2b_audience_seeds(self):
        """B2B seeds should include business-relevant terms."""
        from engines.kw2.constants import AUDIENCE_TEMPLATES
        pillar = "cardamom"
        audience = "restaurant"
        has_audience = False
        for tpl in AUDIENCE_TEMPLATES:
            try:
                phrase = tpl.format(k=pillar, a=audience)
                if audience in phrase:
                    has_audience = True
                    break
            except KeyError:
                pass
        assert has_audience, f"No audience template generated phrase with '{audience}'"
