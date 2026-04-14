"""Tests for Pepper.pl parser — Vue3 JSON and HTML fallback."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from deal_hunter.sources.pepper import PepperSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse_articles(html: str):
    """Parse HTML into article tags (same as PepperSource._parse_deals entry)."""
    import re

    soup = BeautifulSoup(html, "html.parser")
    return soup.find_all("article", class_=re.compile(r"thread"))


class TestParseVue3:
    """Tests for PepperSource._parse_vue3."""

    def setup_method(self):
        self.source = PepperSource()

    def test_basic_vue3_deal(self):
        html = _load_fixture("pepper_vue3.html")
        articles = _parse_articles(html)
        assert len(articles) == 1

        deal = self.source._parse_vue3(articles[0])
        assert deal is not None
        assert deal.title == "Sony WH-1000XM5 słuchawki bezprzewodowe ANC"
        assert deal.price == 1099
        assert deal.regular_price == 1499
        assert deal.temperature == 245
        assert deal.source == "pepper"
        assert "99001" in deal.id
        assert "pepper.pl/promocje/" in deal.link
        assert deal.image_url == "https://example.com/xm5.jpg"
        assert deal.published_at == "2026-03-20T10:00:00+00:00"
        assert "ANC" in deal.description

    def test_expired_vue3_returns_none(self):
        html = _load_fixture("pepper_vue3_expired.html")
        articles = _parse_articles(html)
        assert len(articles) == 1

        deal = self.source._parse_vue3(articles[0])
        assert deal is None

    def test_no_vue3_div_returns_none(self):
        html = _load_fixture("pepper_html.html")
        articles = _parse_articles(html)
        deal = self.source._parse_vue3(articles[0])
        assert deal is None


class TestParseHtml:
    """Tests for PepperSource._parse_html fallback parser."""

    def setup_method(self):
        self.source = PepperSource()

    def test_basic_html_deal(self):
        html = _load_fixture("pepper_html.html")
        articles = _parse_articles(html)
        assert len(articles) == 1

        deal = self.source._parse_html(articles[0], "https://www.pepper.pl")
        assert deal is not None
        assert deal.title == "Sennheiser Momentum 4 Wireless ANC"
        assert deal.price == 1299
        assert deal.regular_price == 1599
        assert deal.temperature == 87
        assert deal.source == "pepper"
        assert "pepper.pl/promocje/sennheiser" in deal.link
        assert deal.image_url == "https://example.com/momentum4.jpg"
        assert deal.published_at == "2026-03-22T14:30:00+00:00"

    def test_expired_html_returns_none(self):
        html = _load_fixture("pepper_html_expired.html")
        articles = _parse_articles(html)
        assert len(articles) == 1

        deal = self.source._parse_html(articles[0], "https://www.pepper.pl")
        assert deal is None


class TestParseDeals:
    """Tests for PepperSource._parse_deals (integration of both parsers)."""

    def setup_method(self):
        self.source = PepperSource()

    def test_multi_deal_page(self):
        html = _load_fixture("pepper_multi.html")
        deals = self.source._parse_deals(html)
        assert len(deals) == 2

        # First deal parsed via Vue3
        assert deals[0].title == "Sony WH-1000XM5 czarne"
        assert deals[0].price == 1099

        # Second deal parsed via HTML fallback
        assert deals[1].title == "Jabra Elite 85h ANC Bluetooth"
        assert deals[1].price == 599
