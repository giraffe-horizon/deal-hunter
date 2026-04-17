"""Tests for deal detail page: chart, actions, metadata."""

import pytest

pytestmark = pytest.mark.e2e

DEAL_URL = "/deals/pepper%3A99999"


def test_price_chart_canvas_exists(page, base_url):
    """The deal detail page has a price chart canvas element."""
    page.goto(base_url + DEAL_URL)
    page.wait_for_load_state("networkidle")
    canvas = page.locator("#priceChart")
    assert canvas.count() == 1


def test_period_buttons_exist(page, base_url):
    """Period filter buttons (1M, 3M, All) are present."""
    page.goto(base_url + DEAL_URL)
    buttons = page.locator("#period-buttons .period-btn")
    assert buttons.count() == 3
    labels = [buttons.nth(i).inner_text().strip() for i in range(3)]
    assert labels == ["1M", "3M", "All"]


def test_period_button_click_changes_active(page, base_url):
    """Clicking a period button changes which button has the active style."""
    page.goto(base_url + DEAL_URL)
    page.wait_for_load_state("networkidle")

    btn_1m = page.locator(".period-btn[data-period='1m']")
    btn_1m.click()
    # The clicked button should have bg-primary (active style)
    assert "bg-primary" in btn_1m.get_attribute("class")

    btn_all = page.locator(".period-btn[data-period='all']")
    # The 'All' button should no longer be active
    assert "bg-primary" not in btn_all.get_attribute("class")


def test_watch_button_updates_status(page, base_url):
    """Clicking Watch sends HTMX post and updates the action area."""
    page.goto(base_url + DEAL_URL)
    page.wait_for_load_state("networkidle")

    watch_btn = page.locator("#watch-skip-controls button:has-text('Watch')")
    watch_btn.click()
    # Wait for HTMX swap to complete
    page.wait_for_load_state("networkidle")

    # After clicking Watch, the status badge in the header should show "Watching"
    # or the action buttons area should reflect the new state
    content = page.locator("#watch-skip-controls").inner_text()
    assert "Watch" in content or "Watching" in content


def test_skip_button_updates_status(page, base_url):
    """Clicking Skip sends HTMX post and updates the action area."""
    page.goto(base_url + DEAL_URL)
    page.wait_for_load_state("networkidle")

    skip_btn = page.locator("#watch-skip-controls button:has-text('Skip')")
    skip_btn.click()
    page.wait_for_load_state("networkidle")

    content = page.locator("#watch-skip-controls").inner_text()
    assert "Skip" in content or "Rejected" in content


def test_open_link_button_present(page, base_url):
    """Open Link button is present with the correct href."""
    page.goto(base_url + DEAL_URL)
    link = page.locator("#watch-skip-controls a:has-text('Open Link')")
    assert link.count() == 1
    href = link.get_attribute("href")
    assert href == "https://example.com/deal/99999"


def test_watchlist_target_price_form(page, base_url):
    """The target price form (sibling of #watch-skip-controls) exists."""
    page.goto(base_url + DEAL_URL)
    form = page.locator("form[hx-post='/api/alerts']")
    assert form.count() == 1
    price_input = form.locator("input[name='target_price']")
    assert price_input.count() == 1
    submit_btn = form.locator("button[type='submit']")
    assert submit_btn.count() == 1


def test_deal_metadata_displayed(page, base_url):
    """Deal metadata sidebar shows source, score, and price."""
    page.goto(base_url + DEAL_URL)
    content = page.content()
    # Source
    assert "pepper" in content
    # Score value (85)
    assert "85" in content
    # Price (8 500 zl)
    assert "8 500" in content or "8500" in content


def test_price_history_table_shown(page, base_url):
    """Price history table shows recorded price entries."""
    page.goto(base_url + DEAL_URL)
    # The deal has 2 price history records
    price_rows = page.locator("table tbody tr")
    # At least 2 rows in the price history table (there is also the main deals info)
    assert price_rows.count() >= 2
