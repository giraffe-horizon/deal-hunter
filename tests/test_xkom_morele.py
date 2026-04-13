"""Tests for x-kom YAML store definition.

NOTE: x-kom.pl uses React client-side rendering and is protected by Cloudflare.
Live HTTP scraping will receive a Cloudflare challenge page rather than product HTML.
These tests verify that the YAML store definition and CSS selectors work correctly
against pre-rendered HTML (as provided by the fixture), not against live requests.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestXkomStore:
    """Tests for x-kom YAML store parsing."""

    def test_xkom_store_registered(self):
        from sources import SOURCE_REGISTRY

        assert "xkom" in SOURCE_REGISTRY, (
            "xkom store not registered — ensure stores/xkom.yaml exists and has a valid 'name' key"
        )

    def test_xkom_store_parses_fixture(self):
        from sources import SOURCE_REGISTRY

        source_cls = SOURCE_REGISTRY["xkom"]
        source = source_cls()

        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")

        with (
            patch.object(source, "_fetch_page", return_value=html),
            patch.object(source, "_rate_limit"),
        ):
            deals = source.fetch_deals({"queries": ["monitor"]})

        assert len(deals) >= 1, "Expected at least one deal parsed from fixture"
        for deal in deals:
            assert deal.title, f"Deal title should not be empty: {deal}"
            assert deal.source == "xkom", f"Expected source 'xkom', got '{deal.source}'"
            assert deal.link, f"Deal link should not be empty: {deal}"

    def test_xkom_parses_three_products(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        assert store_def is not None, "stores/xkom.yaml not found"

        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        assert len(deals) == 3, f"Expected 3 deals, got {len(deals)}"

    def test_xkom_product_titles(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        titles = [d.title for d in deals]
        assert any("Dell" in t for t in titles), f"Expected Dell monitor in titles: {titles}"
        assert any("LG" in t for t in titles), f"Expected LG monitor in titles: {titles}"
        assert any("Samsung" in t for t in titles), f"Expected Samsung monitor in titles: {titles}"

    def test_xkom_product_prices(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        prices = [d.price for d in deals]
        assert 1799 in prices, f"Expected Dell price 1799 PLN in {prices}"
        assert 2399 in prices, f"Expected LG price 2399 PLN in {prices}"
        assert 999 in prices, f"Expected Samsung price 999 PLN in {prices}"

    def test_xkom_product_links(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        for deal in deals:
            assert deal.link.startswith("https://www.x-kom.pl"), (
                f"Expected absolute x-kom.pl link, got: {deal.link}"
            )

    def test_xkom_product_ids(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        ids = [d.id for d in deals]
        assert "xkom:123456" in ids, f"Expected xkom:123456 in {ids}"
        assert "xkom:234567" in ids, f"Expected xkom:234567 in {ids}"
        assert "xkom:345678" in ids, f"Expected xkom:345678 in {ids}"

    def test_xkom_product_images(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        for deal in deals:
            assert deal.image_url, f"Expected image_url for deal: {deal.title}"
            assert "x-kom.pl" in deal.image_url or deal.image_url.startswith("https://"), (
                f"Unexpected image URL: {deal.image_url}"
            )

    def test_xkom_regular_prices(self):
        """Products with OldPrice should have regular_price populated."""
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("xkom")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "xkom_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.x-kom.pl/szukaj?q=monitor")

        # Dell (index 0) and Samsung (index 2) have old prices in fixture
        deals_by_id = {d.id: d for d in deals}
        dell = deals_by_id.get("xkom:123456")
        samsung = deals_by_id.get("xkom:345678")
        lg = deals_by_id.get("xkom:234567")

        if dell:
            assert dell.regular_price == 2099, (
                f"Expected Dell regular_price=2099, got {dell.regular_price}"
            )
        if samsung:
            assert samsung.regular_price == 1199, (
                f"Expected Samsung regular_price=1199, got {samsung.regular_price}"
            )
        if lg:
            assert lg.regular_price == 0, (
                f"Expected LG regular_price=0 (no old price), got {lg.regular_price}"
            )

    def test_xkom_store_type_is_search(self):
        from sources.yaml_source import load_store_definition

        store_def = load_store_definition("xkom")
        assert store_def["type"] == "search"
        assert "{query}" in store_def["search_url"]

    def test_xkom_store_base_url(self):
        from sources.yaml_source import load_store_definition

        store_def = load_store_definition("xkom")
        assert store_def["base_url"] == "https://www.x-kom.pl"


class TestMoreleStore:
    """Tests for Morele YAML store parsing.

    NOTE: morele.net may be protected by Cloudflare in some configurations.
    These tests verify that the YAML store definition and CSS selectors work
    correctly against pre-rendered HTML (the fixture), not against live requests.
    The selectors were verified against a live response from morele.net.
    """

    def test_morele_store_registered(self):
        from sources import SOURCE_REGISTRY

        assert "morele" in SOURCE_REGISTRY, (
            "morele store not registered — ensure stores/morele.yaml"
            " exists and has a valid 'name' key"
        )

    def test_morele_store_parses_fixture(self):
        from unittest.mock import patch

        from sources import SOURCE_REGISTRY

        source_cls = SOURCE_REGISTRY["morele"]
        source = source_cls()

        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")

        with (
            patch.object(source, "_fetch_page", return_value=html),
            patch.object(source, "_rate_limit"),
        ):
            deals = source.fetch_deals({"queries": ["monitor"]})

        assert len(deals) >= 1, "Expected at least one deal parsed from fixture"
        for deal in deals:
            assert deal.title, f"Deal title should not be empty: {deal}"
            assert deal.source == "morele", f"Expected source 'morele', got '{deal.source}'"
            assert deal.link, f"Deal link should not be empty: {deal}"

    def test_morele_parses_three_products(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        assert store_def is not None, "stores/morele.yaml not found"

        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        assert len(deals) == 3, f"Expected 3 deals, got {len(deals)}"

    def test_morele_product_titles(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        titles = [d.title for d in deals]
        assert any("iiyama" in t for t in titles), f"Expected iiyama monitor in titles: {titles}"
        assert any("LG" in t for t in titles), f"Expected LG monitor in titles: {titles}"
        assert any("Samsung" in t for t in titles), f"Expected Samsung monitor in titles: {titles}"

    def test_morele_product_prices(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        prices = [d.price for d in deals]
        assert 469 in prices, f"Expected iiyama price 469 PLN in {prices}"
        assert 349 in prices, f"Expected LG price 349 PLN in {prices}"
        assert 899 in prices, f"Expected Samsung price 899 PLN in {prices}"

    def test_morele_product_links_are_absolute(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        for deal in deals:
            assert deal.link.startswith("https://www.morele.net"), (
                f"Expected absolute morele.net link, got: {deal.link}"
            )

    def test_morele_product_ids(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        ids = [d.id for d in deals]
        assert "morele:15571831" in ids, f"Expected morele:15571831 in {ids}"
        assert "morele:15532596" in ids, f"Expected morele:15532596 in {ids}"
        assert "morele:14987654" in ids, f"Expected morele:14987654 in {ids}"

    def test_morele_product_images(self):
        from sources.yaml_source import YamlSource, load_store_definition

        store_def = load_store_definition("morele")
        source = YamlSource(store_def)
        html = (FIXTURES_DIR / "morele_search.html").read_text(encoding="utf-8")
        deals = source._parse_page(html, "https://www.morele.net/wyszukiwarka/?q=monitor")

        for deal in deals:
            assert deal.image_url, f"Expected image_url for deal: {deal.title}"
            assert "morele.net" in deal.image_url or deal.image_url.startswith("https://"), (
                f"Unexpected image URL: {deal.image_url}"
            )

    def test_morele_store_type_is_search(self):
        from sources.yaml_source import load_store_definition

        store_def = load_store_definition("morele")
        assert store_def["type"] == "search"
        assert "{query}" in store_def["search_url"]

    def test_morele_store_base_url(self):
        from sources.yaml_source import load_store_definition

        store_def = load_store_definition("morele")
        assert store_def["base_url"] == "https://www.morele.net"

    def test_morele_search_url_contains_query(self):
        from sources.yaml_source import load_store_definition

        store_def = load_store_definition("morele")
        search_url = store_def["search_url"]
        assert "wyszukiwarka" in search_url, f"Expected 'wyszukiwarka' in search_url: {search_url}"
        assert "{query}" in search_url
