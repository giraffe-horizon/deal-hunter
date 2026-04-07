"""E2E tests for the Scoring Tuner page: index, rule editor, simulate, save."""

import pytest

pytestmark = pytest.mark.e2e


def test_tuner_index_shows_profile_links(page, base_url):
    """The tuner index page lists profile links including 'bikes'."""
    page.goto(base_url + "/tuner")
    link = page.locator("a[href='/tuner/bikes']")
    assert link.count() >= 1
    assert "bikes" in page.content()


def test_tuner_profile_shows_score_rules_table(page, base_url):
    """The tuner profile page has a score rules editor table with existing rules."""
    page.goto(base_url + "/tuner/bikes")

    # Score rules table body should have rows with rule inputs
    rules_body = page.locator("#score-rules-body")
    assert rules_body.is_visible()
    rows = rules_body.locator("tr")
    assert rows.count() >= 1

    # Check that a keyword input contains one of the seeded rules
    first_keyword = rules_body.locator(".rule-keyword").first
    assert first_keyword.input_value() != ""


def test_tuner_profile_shows_penalties_table(page, base_url):
    """The tuner profile page has a penalties editor table."""
    page.goto(base_url + "/tuner/bikes")

    penalties_body = page.locator("#penalties-body")
    assert penalties_body.is_visible()
    rows = penalties_body.locator("tr")
    assert rows.count() >= 1


def test_tuner_simulate_button_exists(page, base_url):
    """The Simulate button is visible on the tuner profile page."""
    page.goto(base_url + "/tuner/bikes")
    simulate_btn = page.get_by_role("button", name="Simulate")
    assert simulate_btn.is_visible()


def test_tuner_add_rule_row(page, base_url):
    """Clicking the Add button on score rules adds a new empty row."""
    page.goto(base_url + "/tuner/bikes")

    rules_body = page.locator("#score-rules-body")
    initial_count = rules_body.locator("tr").count()

    # Click the Add button next to Score Rules heading
    add_btn = (
        page.locator("#score-rules-body")
        .locator("..")
        .locator("..")
        .get_by_role("button", name="Add")
    )
    add_btn.click()

    new_count = rules_body.locator("tr").count()
    assert new_count == initial_count + 1


def test_tuner_save_button_exists(page, base_url):
    """The Save Profile button is visible on the tuner profile page."""
    page.goto(base_url + "/tuner/bikes")
    save_btn = page.get_by_role("button", name="Save Profile")
    assert save_btn.is_visible()
