"""Tests for verbose scoring breakdown.

ScoreResult.breakdown, BikeFilter entries, output format.
"""

import sys
from io import StringIO
from unittest.mock import patch

from filters.base import BaseFilter, ScoreResult
from filters.bike_filter import BikeFilter
from sources.base import Deal


def _make_deal(**kwargs) -> Deal:
    defaults = {
        "id": "test:1",
        "title": "Test Deal",
        "price": 10000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "",
        "temperature": 0,
        "image_url": "",
        "published_at": "2026-03-20T10:00:00+00:00",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


def _base_profile(**overrides) -> dict:
    base = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 5000, "max": 15000},
        "score_rules": {"carbon": 30, "shimano": 20},
        "penalties": {"broken": -50},
        "excluded_words": ["stolen"],
        "required_any": [],
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {},
    }
    base.update(overrides)
    return base


def _bike_profile(**overrides) -> dict:
    base = _base_profile()
    base.update(
        {
            "custom_data": {
                "brand_sizes": {"giant": ["XL", "L"], "trek": ["58", "60"]},
                "generic_good_sizes": ["XL", "58", "59", "60"],
                "excluded_colors": ["yellow", "pink"],
                "race_keywords": ["aero", "race", "sprint"],
            },
        }
    )
    base.update(overrides)
    return base


# ── ScoreResult.breakdown populated correctly ──


class TestBreakdownPopulated:
    def test_breakdown_default_empty(self):
        """ScoreResult.breakdown defaults to empty list."""
        r = ScoreResult(score=0)
        assert r.breakdown == []

    def test_score_rules_in_breakdown(self):
        """Score rules appear in breakdown with correct structure."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Carbon frame shimano 105")
        result = f.score_deal(deal)

        rules = [e for e in result.breakdown if e["type"] == "keyword"]
        assert len(rules) >= 2
        carbon = next(e for e in rules if e["rule"] == "carbon")
        assert carbon["points"] == 30
        assert carbon["source"] in ("title", "description")
        assert carbon["match"] == "carbon"

    def test_penalty_in_breakdown(self):
        """Penalties appear in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Carbon bike broken frame")
        result = f.score_deal(deal)

        penalties = [e for e in result.breakdown if e["type"] == "penalty"]
        assert any(e["rule"] == "broken" and e["points"] == -50 for e in penalties)

    def test_budget_in_breakdown(self):
        """Budget check appears in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Some deal", price=10000)
        result = f.score_deal(deal)

        budget = [e for e in result.breakdown if e["type"] == "budget"]
        assert len(budget) == 1
        assert budget[0]["points"] == 5
        assert budget[0]["rule"] == "budget"

    def test_budget_too_cheap_in_breakdown(self):
        """Too-cheap budget appears in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Cheap deal", price=1000)
        result = f.score_deal(deal)

        budget = [e for e in result.breakdown if e["type"] == "budget"]
        assert len(budget) == 1
        assert budget[0]["points"] == -20

    def test_budget_too_expensive_in_breakdown(self):
        """Too-expensive budget appears in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Expensive deal", price=20000)
        result = f.score_deal(deal)

        budget = [e for e in result.breakdown if e["type"] == "budget"]
        assert len(budget) == 1
        assert budget[0]["points"] == -30

    def test_temperature_in_breakdown(self):
        """Temperature bonus appears in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Deal", temperature=150)
        result = f.score_deal(deal)

        temp = [e for e in result.breakdown if e["type"] == "temperature"]
        assert len(temp) == 1
        assert temp[0]["points"] == 10
        assert "150" in temp[0]["match"]

    def test_cold_temperature_in_breakdown(self):
        """Cold temperature penalty appears in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Deal", temperature=-20)
        result = f.score_deal(deal)

        temp = [e for e in result.breakdown if e["type"] == "temperature"]
        assert len(temp) == 1
        assert temp[0]["points"] == -10

    def test_excluded_word_in_breakdown(self):
        """Excluded word rejection populates breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Stolen bike carbon")
        result = f.score_deal(deal)

        assert result.rejected
        excluded = [e for e in result.breakdown if e["type"] == "excluded"]
        assert len(excluded) == 1
        assert excluded[0]["rule"] == "stolen"

    def test_required_any_reject_in_breakdown(self):
        """required_any rejection populates breakdown."""
        profile = _base_profile(required_any=["12tb", "12 tb"])
        f = BaseFilter(profile)
        deal = _make_deal(title="8TB HDD drive")
        result = f.score_deal(deal)

        assert result.rejected
        req = [e for e in result.breakdown if e["type"] == "required_any"]
        assert len(req) == 1

    def test_regex_rule_in_breakdown(self):
        """Regex score_rules show type='regex' and the matched text."""
        profile = _base_profile(score_rules={"r/\\b(xl|58|59)\\b/": 15})
        f = BaseFilter(profile)
        deal = _make_deal(title="Giant bike XL frame")
        result = f.score_deal(deal)

        regex = [e for e in result.breakdown if e["type"] == "regex"]
        assert len(regex) == 1
        assert regex[0]["points"] == 15
        assert regex[0]["match"] == "xl"

    def test_breakdown_all_types_present(self):
        """A deal that triggers score_rules, penalties, budget, and temperature
        has all types in breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Carbon broken frame", price=10000, temperature=120)
        result = f.score_deal(deal)

        types = {e["type"] for e in result.breakdown}
        assert "keyword" in types
        assert "penalty" in types
        assert "budget" in types
        assert "temperature" in types


# ── BikeFilter breakdown entries ──


class TestBikeFilterBreakdown:
    def test_good_size_in_breakdown(self):
        """Good size match adds size entry to breakdown."""
        f = BikeFilter(_bike_profile())
        deal = _make_deal(title="Giant Defy Advanced carbon XL frame")
        result = f.score_deal(deal)

        size = [e for e in result.breakdown if e["type"] == "size"]
        assert len(size) == 1
        assert size[0]["points"] == 10
        assert "good size" in size[0]["match"]

    def test_wrong_size_in_breakdown(self):
        """Wrong size rejection adds size entry to breakdown."""
        f = BikeFilter(_bike_profile())
        deal = _make_deal(title="Giant Defy Advanced carbon S frame rozmiar S")
        result = f.score_deal(deal)

        assert result.rejected
        size = [e for e in result.breakdown if e["type"] == "size"]
        assert len(size) == 1

    def test_color_penalty_in_breakdown(self):
        """Excluded color adds color entry to breakdown."""
        f = BikeFilter(_bike_profile())
        deal = _make_deal(title="Trek Domane 58 cm carbon yellow frame")
        result = f.score_deal(deal)

        color = [e for e in result.breakdown if e["type"] == "color"]
        assert len(color) == 1
        assert color[0]["points"] == -100
        assert "yellow" in color[0]["match"]

    def test_race_keywords_in_breakdown(self):
        """Race keyword penalties add race entry to breakdown."""
        f = BikeFilter(_bike_profile())
        deal = _make_deal(title="Bike XL carbon aero race frame")
        result = f.score_deal(deal)

        race = [e for e in result.breakdown if e["type"] == "race"]
        assert len(race) == 1
        assert race[0]["points"] == -30  # 2 keywords * -15

    def test_tire_width_in_breakdown(self):
        """Tire width adds tire entry to breakdown."""
        f = BikeFilter(_bike_profile())
        deal = _make_deal(title="Bike XL carbon 40mm tires")
        result = f.score_deal(deal)

        tire = [e for e in result.breakdown if e["type"] == "tire"]
        assert len(tire) == 1
        assert tire[0]["points"] == 20
        assert "40mm" in tire[0]["match"]


# ── Verbose output format ──


class TestVerboseOutput:
    def test_verbose_plain_output(self):
        """Plain text verbose output uses box-drawing characters."""
        from cli.verify import _print_verbose_plain

        deal = _make_deal(title="Carbon bike deal", price=10000, temperature=120)
        f = BaseFilter(_base_profile())
        result = f.score_deal(deal)

        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_verbose_plain(
                [(deal, result)],
                [],
                threshold=40,
                threshold_alert=80,
                currency="PLN",
                top=None,
            )
        output = buf.getvalue()

        assert "\u250c" in output  # top-left corner
        assert "\u2514" in output  # bottom-left corner
        assert "SCORE:" in output
        assert "carbon" in output.lower()
        assert "Final:" in output

    def test_verbose_plain_rejected(self):
        """Rejected deals are shown in verbose mode."""
        from cli.verify import _print_verbose_plain

        deal = _make_deal(title="Stolen bike")
        f = BaseFilter(_base_profile())
        result = f.score_deal(deal)

        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_verbose_plain(
                [], [(deal, result)], threshold=40, threshold_alert=80, currency="PLN", top=None
            )
        output = buf.getvalue()

        assert "REJECTED" in output
        assert "stolen" in output.lower()

    def test_verbose_plain_pass_status(self):
        """Deals above threshold show checkmark, below show X."""
        from cli.verify import _print_verbose_plain

        # Deal above threshold
        deal_good = _make_deal(title="Carbon shimano deal", price=10000, temperature=120)
        f = BaseFilter(_base_profile())
        result_good = f.score_deal(deal_good)

        # Deal below threshold
        deal_bad = _make_deal(title="Random deal", price=10000)
        result_bad = f.score_deal(deal_bad)

        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_verbose_plain(
                [(deal_good, result_good), (deal_bad, result_bad)],
                [],
                threshold=40,
                threshold_alert=80,
                currency="PLN",
                top=None,
            )
        output = buf.getvalue()
        assert "\u2705" in output
        assert "\u274c" in output

    def test_verbose_top_limit(self):
        """--top N limits output to N deals."""
        from cli.verify import _print_verbose_plain

        deals = []
        f = BaseFilter(_base_profile())
        for i in range(5):
            deal = _make_deal(id=f"test:{i}", title=f"Deal {i}", price=10000)
            result = f.score_deal(deal)
            deals.append((deal, result))

        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_verbose_plain(deals, [], threshold=40, threshold_alert=80, currency="PLN", top=2)
        output = buf.getvalue()

        assert output.count("\u250c") == 2  # only 2 deals rendered
        assert "3 more" in output

    def test_fallback_when_rich_unavailable(self):
        """_print_verbose falls back to plain text when rich is not importable."""
        from cli.verify import print_verbose as _print_verbose

        deal = _make_deal(title="Carbon bike", price=10000)
        f = BaseFilter(_base_profile())
        result = f.score_deal(deal)

        with patch.dict(sys.modules, {"rich": None}):
            buf = StringIO()
            with patch("sys.stdout", buf):
                _print_verbose(
                    [(deal, result)],
                    [],
                    threshold=40,
                    threshold_alert=80,
                    currency="PLN",
                    top=None,
                )
            output = buf.getvalue()
            assert "\u250c" in output  # plain text fallback used


# ── Backwards compatibility ──


class TestBackwardsCompatibility:
    def test_score_result_without_breakdown(self):
        """ScoreResult can be created without breakdown (default empty list)."""
        r = ScoreResult(score=42, plus=["+10 foo"], minus=["-5 bar"])
        assert r.breakdown == []
        assert r.score == 42

    def test_existing_plus_minus_still_populated(self):
        """plus/minus lists are still populated alongside breakdown."""
        f = BaseFilter(_base_profile())
        deal = _make_deal(title="Carbon shimano frame", price=10000, temperature=120)
        result = f.score_deal(deal)

        assert len(result.plus) > 0
        assert any("carbon" in p for p in result.plus)
        assert len(result.breakdown) > 0
