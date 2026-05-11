"""Tests for telegram inline keyboard builder."""

from deal_hunter.notifiers.telegram.keyboards import build_deal_keyboard


def test_keyboard_has_two_rows():
    kb = build_deal_keyboard("https://x", "pepper:1")
    rows = kb["inline_keyboard"]
    assert len(rows) == 2


def test_first_row_keeps_existing_buttons():
    rows = build_deal_keyboard("https://x", "pepper:1")["inline_keyboard"]
    labels = [b["text"] for b in rows[0]]
    assert any("Otwórz" in t for t in labels)
    assert any("Obserwuj" in t for t in labels)
    assert any("Skip" in t for t in labels)


def test_second_row_has_snooze_and_mute():
    rows = build_deal_keyboard("https://x", "pepper:1", snooze_days=30)["inline_keyboard"]
    labels = [b["text"] for b in rows[1]]
    assert any("Drzemka 30d" in t for t in labels)
    assert any("Wycisz" in t for t in labels)


def test_snooze_label_uses_configured_days():
    rows = build_deal_keyboard("https://x", "pepper:1", snooze_days=7)["inline_keyboard"]
    labels = [b["text"] for b in rows[1]]
    assert any("Drzemka 7d" in t for t in labels)


def test_callback_data_for_mute_and_snooze():
    rows = build_deal_keyboard("https://x", "pepper:1")["inline_keyboard"]
    callbacks = {b["text"]: b.get("callback_data") for b in rows[1]}
    mute_cb = next(v for k, v in callbacks.items() if "Wycisz" in k)
    snooze_cb = next(v for k, v in callbacks.items() if "Drzemka" in k)
    assert mute_cb.startswith("mute:")
    assert snooze_cb.startswith("snooze:")
