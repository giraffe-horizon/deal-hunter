"""Tests for the YAML-driven source engine — strategies, field extraction, store loading."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sources.yaml_source import (
    YamlSource,
    load_all_store_definitions,
    load_store_definition,
    make_yaml_source_class,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helpers ──


def _make_source(store_def: dict) -> YamlSource:
    """Create a YamlSource with a given store definition."""
    return YamlSource(store_def)


def _minimal_store(name: str = "test", **overrides) -> dict:
    """Create a minimal store definition."""
    store = {
        "name": name,
        "type": "catalog",
        "base_url": "https://example.com",
        "strategies": ["css"],
        "selectors": {
            "products": "div.product",
            "title": "h2",
            "price": "span.price",
            "link": "a@href",
            "image": "img@src",
        },
    }
    store.update(overrides)
    return store


# ── CSS Strategy Tests ──


class TestCSSStrategy:
    """Tests for CSS selector-based parsing."""

    def test_basic_product_extraction(self):
        store = _minimal_store()
        source = _make_source(store)
        html = """
        <div class="product">
            <h2>Widget Pro</h2>
            <span class="price">299,00 zł</span>
            <a href="/products/123">Link</a>
            <img src="https://example.com/img.jpg" />
        </div>
        """
        deals = source._parse_css(html, "https://example.com/page")
        assert len(deals) == 1
        assert deals[0].title == "Widget Pro"
        assert deals[0].price == 299
        assert deals[0].link == "https://example.com/products/123"
        assert deals[0].image_url == "https://example.com/img.jpg"
        assert deals[0].source == "test"

    def test_multiple_products(self):
        store = _minimal_store()
        source = _make_source(store)
        html = """
        <div class="product">
            <h2>Item A</h2>
            <span class="price">100 zł</span>
            <a href="/a">Link</a>
            <img src="/img-a.jpg" />
        </div>
        <div class="product">
            <h2>Item B</h2>
            <span class="price">200 zł</span>
            <a href="/b">Link</a>
            <img src="/img-b.jpg" />
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert len(deals) == 2
        assert deals[0].title == "Item A"
        assert deals[1].title == "Item B"

    def test_missing_title_skips_product(self):
        store = _minimal_store()
        source = _make_source(store)
        html = """
        <div class="product">
            <span class="price">100 zł</span>
            <a href="/x">Link</a>
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert deals == []

    def test_fallback_selectors_comma_separated(self):
        store = _minimal_store()
        store["selectors"]["title"] = "h2.primary, h3.secondary"
        source = _make_source(store)
        html = """
        <div class="product">
            <h3 class="secondary">Fallback Title</h3>
            <span class="price">50 zł</span>
            <a href="/x">Link</a>
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert len(deals) == 1
        assert deals[0].title == "Fallback Title"

    def test_id_extraction_from_data_attribute(self):
        store = _minimal_store()
        store["selectors"]["id"] = "@data-pid"
        source = _make_source(store)
        html = """
        <div class="product" data-pid="42">
            <h2>Product</h2>
            <span class="price">100 zł</span>
            <a href="/42">Link</a>
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert deals[0].id == "test:42"

    def test_id_fallback_to_link_digits(self):
        store = _minimal_store()
        source = _make_source(store)
        html = """
        <div class="product">
            <h2>Product</h2>
            <span class="price">100 zł</span>
            <a href="/products/789">Link</a>
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert deals[0].id == "test:789"

    def test_regular_price_extraction(self):
        store = _minimal_store()
        store["selectors"]["regular_price"] = "span.old-price"
        source = _make_source(store)
        html = """
        <div class="product">
            <h2>Sale Item</h2>
            <span class="price">79 zł</span>
            <span class="old-price">119 zł</span>
            <a href="/sale">Link</a>
        </div>
        """
        deals = source._parse_css(html, "https://example.com")
        assert deals[0].price == 79
        assert deals[0].regular_price == 119

    def test_relative_url_resolution(self):
        store = _minimal_store()
        source = _make_source(store)
        html = """
        <div class="product">
            <h2>Relative</h2>
            <span class="price">10 zł</span>
            <a href="/item/5">Link</a>
            <img src="/images/5.jpg" />
        </div>
        """
        deals = source._parse_css(html, "https://example.com/page")
        assert deals[0].link == "https://example.com/item/5"
        assert deals[0].image_url == "https://example.com/images/5.jpg"

    def test_no_products_selector_returns_empty(self):
        store = _minimal_store()
        store["selectors"]["products"] = ""
        source = _make_source(store)
        deals = source._parse_css("<html></html>", "https://example.com")
        assert deals == []


# ── JSON-LD Strategy Tests ──


class TestJSONLDStrategy:
    """Tests for JSON-LD (schema.org) parsing."""

    def test_item_list(self):
        store = _minimal_store(name="shop")
        source = _make_source(store)
        jsonld = json.dumps(
            {
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "item": {
                            "@type": "Product",
                            "name": "Widget",
                            "url": "https://shop.com/widget",
                            "sku": "W001",
                            "image": "https://shop.com/w.jpg",
                            "offers": {"price": "299.00"},
                        }
                    },
                    {
                        "item": {
                            "@type": "Product",
                            "name": "Gadget",
                            "url": "/gadget",
                            "sku": "G002",
                            "offers": {"price": "149"},
                        }
                    },
                ],
            }
        )
        html = f'<html><head><script type="application/ld+json">{jsonld}</script></head></html>'
        deals = source._parse_jsonld(html, "https://shop.com/page")
        assert len(deals) == 2
        assert deals[0].title == "Widget"
        assert deals[0].price == 299
        assert deals[0].id == "shop:W001"
        assert deals[0].image_url == "https://shop.com/w.jpg"
        assert deals[1].title == "Gadget"
        assert deals[1].price == 149
        assert deals[1].link == "https://example.com/gadget"

    def test_single_product(self):
        store = _minimal_store(name="solo")
        source = _make_source(store)
        jsonld = json.dumps(
            {
                "@type": "Product",
                "name": "Solo Product",
                "url": "https://solo.com/p/1",
                "productID": "SP1",
                "offers": [{"price": "599"}],
                "image": ["https://solo.com/img1.jpg", "https://solo.com/img2.jpg"],
            }
        )
        html = f'<html><head><script type="application/ld+json">{jsonld}</script></head></html>'
        deals = source._parse_jsonld(html, "https://solo.com")
        assert len(deals) == 1
        assert deals[0].title == "Solo Product"
        assert deals[0].price == 599
        assert deals[0].id == "solo:SP1"
        assert deals[0].image_url == "https://solo.com/img1.jpg"

    def test_no_jsonld_returns_empty(self):
        store = _minimal_store()
        source = _make_source(store)
        deals = source._parse_jsonld("<html><body>No scripts</body></html>", "https://x.com")
        assert deals == []

    def test_invalid_json_ignored(self):
        store = _minimal_store()
        source = _make_source(store)
        html = (
            '<html><head><script type="application/ld+json">not valid json</script></head></html>'
        )
        deals = source._parse_jsonld(html, "https://x.com")
        assert deals == []

    def test_list_of_jsonld_objects(self):
        store = _minimal_store(name="multi")
        source = _make_source(store)
        jsonld = json.dumps(
            [
                {"@type": "Organization", "name": "Org"},
                {
                    "@type": "ItemList",
                    "itemListElement": [
                        {
                            "item": {
                                "name": "Found",
                                "url": "/found",
                                "sku": "F1",
                                "offers": {"price": "10"},
                            }
                        },
                    ],
                },
            ]
        )
        html = f'<html><head><script type="application/ld+json">{jsonld}</script></head></html>'
        deals = source._parse_jsonld(html, "https://multi.com")
        assert len(deals) == 1
        assert deals[0].title == "Found"


# ── GTM dataLayer Strategy Tests ──


class TestGTMStrategy:
    """Tests for GTM data-gtm-impression parsing."""

    def test_basic_gtm_impression(self):
        store = _minimal_store(name="canyon", base_url="https://www.canyon.com")
        source = _make_source(store)
        gtm_data = json.dumps(
            {
                "name": "Endurace CF SL 8",
                "id": "3456",
                "price": 8999,
                "discount": 2000,
                "variant": "Stealth",
                "category": "Road/Endurance",
            }
        )
        html = f"""
        <div data-gtm-impression='{gtm_data}'>
            <a href="/en-pl/endurace-cf-sl-8">Endurace CF SL 8</a>
            <img src="/images/endurace.jpg" />
        </div>
        """
        deals = source._parse_gtm(html, "https://www.canyon.com/outlet")
        assert len(deals) == 1
        d = deals[0]
        assert d.title == "Endurace CF SL 8"
        assert d.price == 8999
        assert d.regular_price == 10999
        assert d.id == "canyon:3456"
        assert d.link == "https://www.canyon.com/en-pl/endurace-cf-sl-8"
        assert d.image_url == "https://www.canyon.com/images/endurace.jpg"
        assert "Color: Stealth" in d.description
        assert "Road/Endurance" in d.description

    def test_gtm_no_discount(self):
        store = _minimal_store(name="gtmshop", base_url="https://shop.com")
        source = _make_source(store)
        gtm_data = json.dumps({"name": "Basic Item", "id": "100", "price": 500})
        html = f"<div data-gtm-impression='{gtm_data}'><a href=\"/item\">x</a></div>"
        deals = source._parse_gtm(html, "https://shop.com")
        assert len(deals) == 1
        assert deals[0].regular_price == 0

    def test_gtm_no_elements_returns_empty(self):
        store = _minimal_store()
        source = _make_source(store)
        deals = source._parse_gtm("<html><body>Nothing</body></html>", "https://x.com")
        assert deals == []

    def test_gtm_invalid_json_skipped(self):
        store = _minimal_store()
        source = _make_source(store)
        html = '<div data-gtm-impression="not valid json"><a href="/">x</a></div>'
        deals = source._parse_gtm(html, "https://x.com")
        assert deals == []


# ── Strategy Dispatch Tests ──


class TestStrategyDispatch:
    """Tests for _parse_page strategy ordering."""

    def test_first_strategy_wins(self):
        store = _minimal_store(name="multi")
        store["strategies"] = ["json-ld", "css"]
        source = _make_source(store)

        # HTML has both JSON-LD and CSS products
        jsonld = json.dumps(
            {
                "@type": "Product",
                "name": "JSONLD Product",
                "url": "/jl",
                "sku": "JL1",
                "offers": {"price": "100"},
            }
        )
        html = f"""
        <html>
        <head><script type="application/ld+json">{jsonld}</script></head>
        <body>
            <div class="product">
                <h2>CSS Product</h2>
                <span class="price">200 zł</span>
                <a href="/css">x</a>
            </div>
        </body></html>
        """
        deals = source._parse_page(html, "https://example.com")
        assert len(deals) == 1
        assert deals[0].title == "JSONLD Product"

    def test_fallback_to_second_strategy(self):
        store = _minimal_store()
        store["strategies"] = ["json-ld", "css"]
        source = _make_source(store)

        # HTML has only CSS products
        html = """
        <html><body>
            <div class="product">
                <h2>CSS Only</h2>
                <span class="price">50 zł</span>
                <a href="/css">x</a>
            </div>
        </body></html>
        """
        deals = source._parse_page(html, "https://example.com")
        assert len(deals) == 1
        assert deals[0].title == "CSS Only"


# ── Field Extraction Tests ──


class TestFieldExtraction:
    """Tests for _extract_field helper."""

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").find()

    def test_text_extraction(self):
        el = self._make_soup('<div><span class="name">Hello World</span></div>')
        assert YamlSource._extract_field(el, "span.name") == "Hello World"

    def test_attribute_extraction(self):
        el = self._make_soup('<div><a href="/link">Click</a></div>')
        assert YamlSource._extract_field(el, "a@href") == "/link"

    def test_self_attribute(self):
        el = self._make_soup('<div data-id="42"><span>text</span></div>')
        assert YamlSource._extract_field(el, "@data-id") == "42"

    def test_comma_fallback(self):
        el = self._make_soup('<div><span class="alt">Fallback</span></div>')
        assert YamlSource._extract_field(el, "span.primary, span.alt") == "Fallback"

    def test_empty_selector(self):
        el = self._make_soup("<div>text</div>")
        assert YamlSource._extract_field(el, "") == ""

    def test_no_match_returns_empty(self):
        el = self._make_soup("<div>text</div>")
        assert YamlSource._extract_field(el, "span.missing") == ""


# ── URL Resolution Tests ──


class TestURLResolution:
    def test_absolute_url_unchanged(self):
        source = _make_source(_minimal_store())
        assert (
            source._resolve_url("https://other.com/x", "https://example.com")
            == "https://other.com/x"
        )

    def test_relative_url_resolved(self):
        source = _make_source(_minimal_store(base_url="https://example.com"))
        assert (
            source._resolve_url("/item/5", "https://example.com/page")
            == "https://example.com/item/5"
        )

    def test_empty_url(self):
        source = _make_source(_minimal_store())
        assert source._resolve_url("", "https://example.com") == ""


# ── Search URL Building Tests ──


class TestSearchURL:
    def test_basic_search_url(self):
        store = _minimal_store(
            type="search",
            search_url="https://shop.com/search?q={query}",
        )
        source = _make_source(store)
        url = source._build_search_url("test query")
        assert url == "https://shop.com/search?q=test+query"

    def test_search_url_with_category(self):
        store = _minimal_store(
            type="search",
            search_url="https://shop.com/search?q={query}",
            search_url_category="https://shop.com/{category}?q={query}",
        )
        source = _make_source(store)
        url = source._build_search_url("test", category="electronics")
        assert url == "https://shop.com/electronics?q=test"

    def test_search_url_no_category_uses_default(self):
        store = _minimal_store(
            type="search",
            search_url="https://shop.com/search?q={query}",
            search_url_category="https://shop.com/{category}?q={query}",
        )
        source = _make_source(store)
        url = source._build_search_url("test", category="")
        assert url == "https://shop.com/search?q=test"


# ── Pagination Tests ──


class TestPagination:
    def test_page_1_unchanged(self):
        url = YamlSource._paginate_url("https://shop.com/list", 1, {"param": "page"})
        assert url == "https://shop.com/list"

    def test_page_2_adds_param(self):
        url = YamlSource._paginate_url("https://shop.com/list", 2, {"param": "page"})
        assert "page=2" in url

    def test_custom_param_name(self):
        url = YamlSource._paginate_url("https://shop.com/list", 3, {"param": "p"})
        assert "p=3" in url

    def test_existing_query_params_preserved(self):
        url = YamlSource._paginate_url("https://shop.com/list?sort=price", 2, {"param": "page"})
        assert "sort=price" in url
        assert "page=2" in url


# ── Store Loading Tests ──


class TestStoreLoading:
    def test_load_single_store(self):
        store = load_store_definition("ceneo")
        assert store is not None
        assert store["name"] == "ceneo"
        assert store["type"] == "search"

    def test_load_nonexistent_store(self):
        store = load_store_definition("nonexistent_store_xyz")
        assert store is None

    def test_load_all_stores(self):
        stores = load_all_store_definitions()
        assert len(stores) >= 7
        expected = {
            "ceneo",
            "proshop",
            "canyon",
            "rowertour",
            "centrumrowerowe",
            "sprint",
            "veloshop",
        }
        assert expected.issubset(set(stores.keys()))

    def test_all_stores_have_required_fields(self):
        stores = load_all_store_definitions()
        for name, store in stores.items():
            assert "name" in store, f"{name} missing 'name'"
            assert "strategies" in store or "selectors" in store, (
                f"{name} missing strategies/selectors"
            )


# ── Auto-Discovery / Registry Tests ──


class TestAutoDiscovery:
    def test_yaml_stores_in_registry(self):
        from sources import SOURCE_REGISTRY

        for name in [
            "ceneo",
            "proshop",
            "canyon",
            "rowertour",
            "centrumrowerowe",
            "sprint",
            "veloshop",
        ]:
            assert name in SOURCE_REGISTRY, f"{name} not in SOURCE_REGISTRY"

    def test_yaml_source_instantiation(self):
        from sources import SOURCE_REGISTRY

        for name in ["ceneo", "proshop", "canyon"]:
            source_class = SOURCE_REGISTRY[name]
            source = source_class()
            assert isinstance(source, YamlSource)

    def test_pepper_still_python(self):
        from sources import SOURCE_REGISTRY
        from sources.pepper import PepperSource

        assert SOURCE_REGISTRY["pepper"] is PepperSource

    def test_web_still_python(self):
        from sources import SOURCE_REGISTRY
        from sources.web import WebSource

        assert SOURCE_REGISTRY["web"] is WebSource


# ── Factory Tests ──


class TestMakeYamlSourceClass:
    def test_creates_subclass(self):
        store_def = _minimal_store(name="myshop")
        cls = make_yaml_source_class(store_def)
        assert issubclass(cls, YamlSource)
        instance = cls()
        assert instance._store_name == "myshop"

    def test_class_name_derived_from_store(self):
        cls = make_yaml_source_class(_minimal_store(name="cool_store"))
        assert "CoolStore" in cls.__name__
