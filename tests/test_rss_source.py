"""Tests for RSS/Atom feed source."""

from pathlib import Path
from unittest.mock import patch

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestRssSource:
    """Tests for RssSource parsing."""

    def test_parse_rss_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        assert len(deals) == 3
        assert deals[0].title == "Rower szosowy Canyon Endurace CF rozmiar XL"
        assert deals[0].source == "allegro"
        assert "allegro.pl" in deals[0].link
        assert deals[0].id.startswith("allegro:")

    def test_extract_price_from_title(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        giant = [d for d in deals if "Giant" in d.title][0]
        assert giant.price == 8999

    def test_extract_price_from_description(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        canyon = [d for d in deals if "Canyon" in d.title][0]
        assert canyon.price == 10499

    def test_no_price_returns_zero(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        akc = [d for d in deals if "Akcesoria" in d.title][0]
        assert akc.price == 0

    def test_parse_atom_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "rss_atom.xml").read_text()
        deals = source._parse_feed(xml_content, "example")

        assert len(deals) == 2
        assert deals[0].title == "Laptop Dell XPS - 5 499 zł"
        assert deals[0].source == "example"
        assert deals[0].price == 5499

    def test_atom_price_from_summary(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "rss_atom.xml").read_text()
        deals = source._parse_feed(xml_content, "example")

        monitor = [d for d in deals if "Monitor" in d.title][0]
        assert monitor.price == 1899

    def test_empty_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        deals = source._parse_feed(xml_content, "test")
        assert deals == []

    def test_malformed_xml_returns_empty(self):
        from sources.rss import RssSource

        source = RssSource()
        deals = source._parse_feed("<not>valid xml", "test")
        assert deals == []

    def test_fetch_deals_multiple_feeds(self):
        from sources.rss import RssSource

        source = RssSource()
        rss_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        atom_content = (FIXTURES_DIR / "rss_atom.xml").read_text()

        call_count = 0

        def mock_fetch(url):
            nonlocal call_count
            call_count += 1
            if "allegro" in url:
                return rss_content
            return atom_content

        config = {
            "feeds": [
                {"url": "https://allegro.pl/rss/test", "source_name": "allegro"},
                {"url": "https://example.com/feed.xml", "source_name": "example"},
            ]
        }

        with (
            patch.object(source, "_fetch_page", side_effect=mock_fetch),
            patch.object(source, "_rate_limit"),
        ):
            deals = source.fetch_deals(config)

        assert len(deals) == 5
        assert call_count == 2

    def test_published_at_parsed(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        assert deals[0].published_at != ""

    def test_deal_id_uses_guid(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()
        deals = source._parse_feed(xml_content, "allegro")

        # ID should be deterministic from guid
        assert deals[0].id.startswith("allegro:")

    def test_default_source_name(self):
        from sources.rss import RssSource

        source = RssSource()
        xml_content = (FIXTURES_DIR / "allegro_rss.xml").read_text()

        config = {"feeds": [{"url": "https://example.com/feed.xml"}]}

        with (
            patch.object(source, "_fetch_page", return_value=xml_content),
            patch.object(source, "_rate_limit"),
        ):
            deals = source.fetch_deals(config)

        assert all(d.source == "rss" for d in deals)

    def test_fetch_page_returns_none_skips_feed(self):
        from sources.rss import RssSource

        source = RssSource()
        config = {"feeds": [{"url": "https://example.com/broken"}]}

        with (
            patch.object(source, "_fetch_page", return_value=None),
            patch.object(source, "_rate_limit"),
        ):
            deals = source.fetch_deals(config)

        assert deals == []
