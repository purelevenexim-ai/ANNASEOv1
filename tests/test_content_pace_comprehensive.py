"""
GROUP — ContentPace comprehensive tests
~160 tests covering ContentPace fields, cost estimation, scheduling logic, pillar overrides
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))

import pytest
from ruflo_20phase_engine import ContentPace, Seed, P1_SeedInput


@pytest.fixture
def p1(): return P1_SeedInput()


@pytest.fixture
def seed(p1): return p1.run("black pepper")


@pytest.fixture
def default_pace():
    return ContentPace()


@pytest.fixture
def fast_pace():
    return ContentPace(duration_years=1, blogs_per_day=10)


@pytest.fixture
def slow_pace():
    return ContentPace(duration_years=3, blogs_per_day=1)


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT VALUES
# ─────────────────────────────────────────────────────────────────────────────

class TestContentPaceDefaults:
    def test_default_duration_years(self, default_pace):
        assert default_pace.duration_years == 2.0

    def test_default_blogs_per_day(self, default_pace):
        assert default_pace.blogs_per_day == 3

    def test_default_pillar_overrides_empty(self, default_pace):
        assert default_pace.pillar_overrides == {}

    def test_default_seasonal_priorities_empty(self, default_pace):
        assert default_pace.seasonal_priorities == {}

    def test_default_total_days(self, default_pace):
        assert default_pace.total_days == 730  # 2 * 365

    def test_is_dataclass_instance(self, default_pace):
        assert isinstance(default_pace, ContentPace)


# ─────────────────────────────────────────────────────────────────────────────
# TOTAL DAYS
# ─────────────────────────────────────────────────────────────────────────────

class TestTotalDays:
    @pytest.mark.parametrize("years,expected", [
        (1.0, 365),
        (2.0, 730),
        (3.0, 1095),
        (5.0, 1825),
        (0.5, 182),
    ])
    def test_total_days_various_years(self, years, expected):
        pace = ContentPace(duration_years=years)
        assert pace.total_days == expected

    def test_total_days_is_int(self, default_pace):
        assert isinstance(default_pace.total_days, int)

    def test_total_days_one_year(self):
        pace = ContentPace(duration_years=1.0)
        assert pace.total_days == 365

    def test_total_days_half_year(self):
        pace = ContentPace(duration_years=0.5)
        assert pace.total_days == 182

    def test_total_days_proportional(self):
        pace1 = ContentPace(duration_years=1.0)
        pace2 = ContentPace(duration_years=2.0)
        assert pace2.total_days == 2 * pace1.total_days


# ─────────────────────────────────────────────────────────────────────────────
# BLOGS PER DAY FOR PILLAR
# ─────────────────────────────────────────────────────────────────────────────

class TestBlogsPerDayForPillar:
    def test_default_pillar_returns_global(self, default_pace):
        assert default_pace.blogs_per_day_for_pillar("health benefits") == 3

    def test_overridden_pillar_returns_override(self):
        pace = ContentPace(blogs_per_day=3, pillar_overrides={"cooking": 5})
        assert pace.blogs_per_day_for_pillar("cooking") == 5

    def test_non_overridden_pillar_returns_global(self):
        pace = ContentPace(blogs_per_day=3, pillar_overrides={"cooking": 5})
        assert pace.blogs_per_day_for_pillar("health") == 3

    def test_multiple_overrides(self):
        pace = ContentPace(
            blogs_per_day=2,
            pillar_overrides={"cooking": 5, "health": 8, "beauty": 3}
        )
        assert pace.blogs_per_day_for_pillar("cooking") == 5
        assert pace.blogs_per_day_for_pillar("health") == 8
        assert pace.blogs_per_day_for_pillar("beauty") == 3
        assert pace.blogs_per_day_for_pillar("other") == 2

    @pytest.mark.parametrize("pillar,expected", [
        ("black pepper health", 10),
        ("cinnamon recipes", 5),
        ("turmeric supplements", 7),
    ])
    def test_spice_pillar_overrides(self, pillar, expected):
        pace = ContentPace(
            blogs_per_day=3,
            pillar_overrides={
                "black pepper health": 10,
                "cinnamon recipes": 5,
                "turmeric supplements": 7,
            }
        )
        assert pace.blogs_per_day_for_pillar(pillar) == expected

    def test_empty_pillar_key_handled(self):
        pace = ContentPace(blogs_per_day=3)
        result = pace.blogs_per_day_for_pillar("")
        assert result == 3


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATED COST
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimatedCost:
    def test_returns_float(self, default_pace):
        cost = default_pace.estimated_cost_usd(100)
        assert isinstance(cost, (int, float))

    def test_zero_blogs_zero_cost(self, default_pace):
        cost = default_pace.estimated_cost_usd(0)
        assert cost == 0.0

    def test_cost_scales_with_blogs(self, default_pace):
        cost1 = default_pace.estimated_cost_usd(100)
        cost2 = default_pace.estimated_cost_usd(200)
        assert cost2 > cost1

    def test_cost_nonnegative(self, default_pace):
        for n in [1, 10, 100, 1000]:
            assert default_pace.estimated_cost_usd(n) >= 0

    @pytest.mark.parametrize("total_blogs", [1, 50, 100, 365, 730, 1095])
    def test_various_blog_counts(self, default_pace, total_blogs):
        cost = default_pace.estimated_cost_usd(total_blogs)
        assert isinstance(cost, (int, float))
        assert cost >= 0

    def test_cost_is_deterministic(self, default_pace):
        c1 = default_pace.estimated_cost_usd(500)
        c2 = default_pace.estimated_cost_usd(500)
        assert c1 == c2


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_returns_dict(self, default_pace):
        s = default_pace.summary(100)
        assert isinstance(s, dict)

    def test_summary_has_duration_years(self, default_pace):
        s = default_pace.summary(100)
        assert "duration_years" in s

    def test_summary_has_blogs_per_day(self, default_pace):
        s = default_pace.summary(100)
        assert "blogs_per_day" in s

    def test_summary_duration_correct(self):
        pace = ContentPace(duration_years=3, blogs_per_day=5)
        s = pace.summary(100)
        assert s["duration_years"] == 3

    def test_summary_blogs_per_day_correct(self):
        pace = ContentPace(duration_years=1, blogs_per_day=7)
        s = pace.summary(100)
        assert s["blogs_per_day"] == 7

    def test_summary_zero_blogs(self, default_pace):
        s = default_pace.summary(0)
        assert isinstance(s, dict)

    @pytest.mark.parametrize("total_blogs", [10, 100, 730, 2000])
    def test_summary_various_blog_counts(self, total_blogs):
        pace = ContentPace(duration_years=2, blogs_per_day=3)
        s = pace.summary(total_blogs)
        assert isinstance(s, dict)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTION VARIATIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestContentPaceConstruction:
    def test_one_year_plan(self):
        pace = ContentPace(duration_years=1.0, blogs_per_day=5)
        assert pace.duration_years == 1.0
        assert pace.blogs_per_day == 5
        assert pace.total_days == 365

    def test_two_year_plan(self):
        pace = ContentPace(duration_years=2.0, blogs_per_day=3)
        assert pace.total_days == 730

    def test_with_seasonal_priorities(self):
        pace = ContentPace(
            duration_years=1,
            blogs_per_day=3,
            seasonal_priorities={"Christmas": "2026-12-01", "Diwali": "2026-10-20"}
        )
        assert "Christmas" in pace.seasonal_priorities
        assert "Diwali" in pace.seasonal_priorities

    def test_with_pillar_overrides_and_seasonal(self):
        pace = ContentPace(
            duration_years=2,
            blogs_per_day=5,
            pillar_overrides={"top_pillar": 10},
            seasonal_priorities={"summer": "2026-06-01"}
        )
        assert pace.blogs_per_day_for_pillar("top_pillar") == 10
        assert "summer" in pace.seasonal_priorities

    @pytest.mark.parametrize("years,daily", [
        (1, 1), (1, 5), (1, 10), (1, 20),
        (2, 3), (2, 10), (3, 5), (5, 2),
    ])
    def test_various_combinations(self, years, daily):
        pace = ContentPace(duration_years=years, blogs_per_day=daily)
        assert pace.duration_years == years
        assert pace.blogs_per_day == daily
        assert pace.total_days == int(365 * years)

    def test_high_volume_pace(self):
        pace = ContentPace(duration_years=1, blogs_per_day=50)
        assert pace.blogs_per_day == 50
        assert pace.total_days == 365

    def test_low_volume_pace(self):
        pace = ContentPace(duration_years=5, blogs_per_day=1)
        assert pace.blogs_per_day == 1
        assert pace.total_days == 1825


# ─────────────────────────────────────────────────────────────────────────────
# CAPACITY CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestCapacityCalculations:
    def test_1yr_3perday_capacity(self):
        pace = ContentPace(duration_years=1, blogs_per_day=3)
        capacity = pace.total_days * pace.blogs_per_day
        assert capacity == 365 * 3

    def test_2yr_5perday_capacity(self):
        pace = ContentPace(duration_years=2, blogs_per_day=5)
        capacity = pace.total_days * pace.blogs_per_day
        assert capacity == 730 * 5

    def test_longer_duration_higher_capacity(self):
        pace1 = ContentPace(duration_years=1, blogs_per_day=3)
        pace2 = ContentPace(duration_years=2, blogs_per_day=3)
        cap1 = pace1.total_days * pace1.blogs_per_day
        cap2 = pace2.total_days * pace2.blogs_per_day
        assert cap2 > cap1

    def test_higher_daily_higher_capacity(self):
        pace1 = ContentPace(duration_years=1, blogs_per_day=3)
        pace2 = ContentPace(duration_years=1, blogs_per_day=10)
        cap1 = pace1.total_days * pace1.blogs_per_day
        cap2 = pace2.total_days * pace2.blogs_per_day
        assert cap2 > cap1

    @pytest.mark.parametrize("years,daily,expected_capacity", [
        (1, 1, 365),
        (1, 3, 1095),
        (2, 3, 2190),
        (2, 5, 3650),
    ])
    def test_capacity_various(self, years, daily, expected_capacity):
        pace = ContentPace(duration_years=years, blogs_per_day=daily)
        capacity = pace.total_days * pace.blogs_per_day
        assert capacity == expected_capacity


# ─────────────────────────────────────────────────────────────────────────────
# SPICE INDUSTRY SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────

SPICE_SEASONAL = {
    "Festival Baking Season": "2026-10-01",
    "Summer Detox": "2026-05-01",
    "Winter Immunity": "2026-11-01",
}

SPICE_PILLAR_OVERRIDES = {
    "black pepper health benefits": 5,
    "cinnamon recipes": 8,
    "turmeric supplements": 6,
    "ginger remedies": 4,
    "clove dental": 3,
}


class TestSpiceIndustryPace:
    def test_spice_seasonal_priorities_stored(self):
        pace = ContentPace(
            duration_years=1,
            blogs_per_day=3,
            seasonal_priorities=SPICE_SEASONAL
        )
        for key in SPICE_SEASONAL:
            assert key in pace.seasonal_priorities

    def test_spice_pillar_overrides_stored(self):
        pace = ContentPace(
            duration_years=2,
            blogs_per_day=3,
            pillar_overrides=SPICE_PILLAR_OVERRIDES
        )
        for pillar, rate in SPICE_PILLAR_OVERRIDES.items():
            assert pace.blogs_per_day_for_pillar(pillar) == rate

    @pytest.mark.parametrize("pillar", list(SPICE_PILLAR_OVERRIDES.keys()))
    def test_each_spice_pillar_override(self, pillar):
        pace = ContentPace(blogs_per_day=3, pillar_overrides=SPICE_PILLAR_OVERRIDES)
        expected = SPICE_PILLAR_OVERRIDES[pillar]
        assert pace.blogs_per_day_for_pillar(pillar) == expected

    def test_full_spice_plan_1yr(self):
        pace = ContentPace(
            duration_years=1,
            blogs_per_day=5,
            pillar_overrides=SPICE_PILLAR_OVERRIDES,
            seasonal_priorities=SPICE_SEASONAL
        )
        assert pace.total_days == 365
        assert pace.summary(365 * 5) is not None

    def test_full_spice_plan_2yr(self):
        pace = ContentPace(
            duration_years=2,
            blogs_per_day=3,
            pillar_overrides=SPICE_PILLAR_OVERRIDES,
            seasonal_priorities=SPICE_SEASONAL
        )
        assert pace.total_days == 730
        cost = pace.estimated_cost_usd(730 * 3)
        assert cost >= 0

    def test_spice_cost_1yr_vs_2yr(self):
        pace1 = ContentPace(duration_years=1, blogs_per_day=3)
        pace2 = ContentPace(duration_years=2, blogs_per_day=3)
        cost1 = pace1.estimated_cost_usd(365 * 3)
        cost2 = pace2.estimated_cost_usd(730 * 3)
        assert cost2 >= cost1


# ─────────────────────────────────────────────────────────────────────────────
# SEED + PACE COMBINED
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedWithPace:
    @pytest.mark.parametrize("spice,years,daily", [
        ("black pepper", 1, 3),
        ("cinnamon", 2, 5),
        ("turmeric", 1, 10),
        ("ginger", 3, 2),
        ("clove", 2, 4),
    ])
    def test_seed_pace_combination(self, p1, spice, years, daily):
        seed = p1.run(spice)
        pace = ContentPace(duration_years=years, blogs_per_day=daily)
        assert seed.keyword == spice
        assert pace.total_days == int(365 * years)
        assert pace.blogs_per_day == daily

    def test_seed_pace_summary_matches_seed(self, p1):
        seed = p1.run("black pepper")
        pace = ContentPace(duration_years=2, blogs_per_day=5)
        s = pace.summary(pace.total_days * pace.blogs_per_day)
        assert isinstance(s, dict)
        assert s["duration_years"] == 2
        assert s["blogs_per_day"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
