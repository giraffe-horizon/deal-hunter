"""Tests for Ceneo.pl parser — product rows and card layouts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sources.ceneo import CeneoSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestParseResults:
    """Tests for CeneoSource._parse_results."""

    def setup_method(self):
        self.source = CeneoSource()

    def test_product_rows(self):
        html = _load_fixture("ceneo_results.html")
        deals = self.source._parse_results(html, "słuchawki ANC")
        assert len(deals) == 3

        # First product
        assert deals[0].title == "Sony WH-1000XM5 Czarne"
        assert deals[0].price == 1099
        assert deals[0].regular_price == 1499
        assert deals[0].source == "ceneo"
        assert "ceneo:" in deals[0].id
        assert deals[0].image_url == "https://example.com/ceneo-xm5.jpg"

        # Second product — no old price
        assert deals[1].title == "Bose QuietComfort Ultra Headphones"
        assert deals[1].price == 1599
        assert deals[1].regular_price == 0

        # Third product
        assert deals[2].title == "JBL Tune 770NC Wireless ANC"
        assert deals[2].price == 299
        assert deals[2].regular_price == 399

    def test_product_id_from_data_pid(self):
        html = _load_fixture("ceneo_results.html")
        deals = self.source._parse_results(html, "test")
        assert deals[0].id == "ceneo:40001"
        assert deals[1].id == "ceneo:40002"

    def test_empty_results(self):
        html = _load_fixture("ceneo_empty.html")
        deals = self.source._parse_results(html, "nonexistent product")
        assert deals == []

    def test_card_layout(self):
        html = _load_fixture("ceneo_cards.html")
        deals = self.source._parse_results(html, "słuchawki")
        assert len(deals) == 2

        assert deals[0].title == "Sennheiser HD 450BT ANC"
        assert deals[0].price == 349
        assert deals[0].source == "ceneo"

        assert deals[1].title == "Sony WF-1000XM5 douszne"
        assert deals[1].price == 899
        assert deals[1].regular_price == 1099
