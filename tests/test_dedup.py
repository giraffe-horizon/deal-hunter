"""Tests for deal deduplication and title normalization."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from deal_hunter import _normalize_title, deduplicate
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
        "published_at": "",
    }
    defaults.update(kwargs)
    return Deal(**defaults)


def test_exact_dedup():
    """Same ID is deduplicated."""
    deals = [
        _make_deal(id="pepper:123", title="Deal A"),
        _make_deal(id="pepper:123", title="Deal A"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_cross_source_dedup():
    """Same title+price from different sources is deduplicated (merged)."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500, source="pepper"),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=8500, source="ceneo"),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_fuzzy_dedup():
    """Similar titles with same price are deduplicated."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Giant Defy Advanced 2 2024 carbon rower szosowy",
            price=8500,
        ),
        _make_deal(
            id="ceneo:2",
            title="Giant Defy Advanced 2 2024 carbon szosowy rower",
            price=8500,
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1


def test_different_price_not_deduped():
    """Same title but very different price is NOT deduplicated."""
    deals = [
        _make_deal(id="pepper:1", title="Giant Defy Advanced 2", price=8500),
        _make_deal(id="ceneo:2", title="Giant Defy Advanced 2", price=12000),
    ]
    result = deduplicate(deals)
    assert len(result) == 2


def test_merge_populates_alt_links():
    """Merged duplicate adds source info to winner's alt_links."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Canyon Endurace CF 7",
            price=9000,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2",
            title="Canyon Endurace CF 7",
            price=9000,
            source="ceneo",
            link="https://ceneo.pl/2",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 1
    assert result[0].alt_links[0]["source"] == "ceneo"
    assert result[0].alt_links[0]["link"] == "https://ceneo.pl/2"
    assert result[0].alt_links[0]["price"] == 9000


def test_merge_price_tolerance():
    """Deals within 5% price tolerance are merged."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Canyon Endurace CF 7",
            price=10000,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2",
            title="Canyon Endurace CF 7",
            price=10300,
            source="ceneo",
            link="https://ceneo.pl/2",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 1


def test_merge_price_outside_tolerance():
    """Deals with >5% price difference are NOT merged."""
    deals = [
        _make_deal(id="pepper:1", title="Canyon Endurace CF 7", price=10000, source="pepper"),
        _make_deal(id="ceneo:2", title="Canyon Endurace CF 7", price=11000, source="ceneo"),
    ]
    result = deduplicate(deals)
    assert len(result) == 2


def test_merge_three_sources():
    """3 sources for same product -> 1 winner with 2 alt_links."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="WD Red 4TB",
            price=500,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2", title="WD Red 4TB", price=510, source="ceneo", link="https://ceneo.pl/2"
        ),
        _make_deal(
            id="morele:3",
            title="WD Red 4TB",
            price=490,
            source="morele",
            link="https://morele.net/3",
        ),
    ]
    result = deduplicate(deals)
    assert len(result) == 1
    assert len(result[0].alt_links) == 2


def test_merge_keeps_first_as_winner():
    """First deal encountered is the winner."""
    deals = [
        _make_deal(
            id="pepper:1",
            title="Product X",
            price=1000,
            source="pepper",
            link="https://pepper.pl/1",
        ),
        _make_deal(
            id="ceneo:2", title="Product X", price=1000, source="ceneo", link="https://ceneo.pl/2"
        ),
    ]
    result = deduplicate(deals)
    assert result[0].source == "pepper"
    assert result[0].link == "https://pepper.pl/1"


def test_merge_zero_price_not_merged():
    """Deals with price=0 are not merged on price tolerance."""
    deals = [
        _make_deal(id="pepper:1", title="Product X", price=0, source="pepper"),
        _make_deal(id="ceneo:2", title="Product X", price=0, source="ceneo"),
    ]
    result = deduplicate(deals)
    assert len(result) == 2


def test_dedup_with_custom_config():
    """Custom dedup config overrides defaults."""
    deals = [
        _make_deal(id="pepper:1", title="Canyon Endurace CF 7", price=10000, source="pepper"),
        _make_deal(id="ceneo:2", title="Canyon Endurace CF 7", price=10800, source="ceneo"),
    ]
    # Default 5% tolerance: 10800 is 8% off from 10000 -> NOT merged
    result = deduplicate(deals)
    assert len(result) == 2

    # With 10% tolerance: 10800 is 8% off -> MERGED
    config = {"price_tolerance": 0.10, "title_similarity": 0.85}
    result = deduplicate(deals, dedup_config=config)
    assert len(result) == 1


def test_dedup_disabled():
    """When dedup enabled=false, only ID dedup occurs."""
    deals = [
        _make_deal(id="pepper:1", title="Same Product", price=1000, source="pepper"),
        _make_deal(id="ceneo:2", title="Same Product", price=1000, source="ceneo"),
    ]
    config = {"enabled": False}
    result = deduplicate(deals, dedup_config=config)
    assert len(result) == 2


# -- _normalize_title tests --


def test_normalize_title_lowercase():
    assert _normalize_title("Sony WH-1000XM5") == "sony wh1000xm5"


def test_normalize_title_strips_punctuation():
    assert _normalize_title("Deal! (wow) - great.") == "deal wow great"


def test_normalize_title_collapses_whitespace():
    assert _normalize_title("  lots   of   spaces  ") == "lots of spaces"


def test_normalize_title_empty():
    assert _normalize_title("") == ""


def test_normalize_title_unicode():
    assert _normalize_title("Słuchawki ANC — super!") == "słuchawki anc super"


def test_telegram_alert_with_alt_links():
    """send_alert includes alt_links in message when present."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=9000,
        source="pepper",
        link="https://pepper.pl/1",
        alt_links=[
            {"source": "ceneo", "link": "https://ceneo.pl/2", "price": 9200},
            {"source": "morele", "link": "https://morele.net/3", "price": 8900},
        ],
    )
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_alert(deal, 85, "ZNALAZŁEM OKAZJĘ", ["keyword1"], [])
        msg = mock_send.call_args[0][0]
        assert "Też w:" in msg
        assert "ceneo" in msg
        assert "morele" in msg


def test_telegram_alert_without_alt_links():
    """send_alert omits 'Też w:' section when alt_links is empty."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=9000,
        source="pepper",
        link="https://pepper.pl/1",
    )
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_alert(deal, 85, "ZNALAZŁEM OKAZJĘ", ["keyword1"], [])
        msg = mock_send.call_args[0][0]
        assert "Też w:" not in msg


def test_telegram_price_drop_with_alt_links():
    """send_price_drop_alert includes alt_links when present."""
    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier("fake-token", "fake-chat")
    deal = _make_deal(
        id="pepper:1",
        title="Canyon Endurace CF 7",
        price=8500,
        source="pepper",
        link="https://pepper.pl/1",
        alt_links=[{"source": "ceneo", "link": "https://ceneo.pl/2", "price": 8700}],
    )
    price_change = {
        "old_price": 9000,
        "new_price": 8500,
        "diff_pln": 500,
        "diff_percent": 5.6,
    }
    with patch.object(notifier, "_send_message") as mock_send:
        notifier.send_price_drop_alert(deal, price_change)
        msg = mock_send.call_args[0][0]
        assert "Też w:" in msg
        assert "ceneo" in msg
