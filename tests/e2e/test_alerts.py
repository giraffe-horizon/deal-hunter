"""E2E tests for the Price Alerts page (`/alerts`).

The backing SQLite table is still named ``watchlist``; only the URL and
user-facing labels use "alerts" / "Price Alerts" now.  The separate
``/watchlist`` page lists offers with ``status='watching'``.
"""

import pytest

pytestmark = pytest.mark.e2e


def test_empty_alerts_shows_empty_state(page, base_url):
    """Alerts page with no items shows an empty state message."""
    page.goto(base_url + "/alerts")
    page.wait_for_load_state("networkidle")
    assert "No price alerts" in page.content()


def test_add_alert_from_deal_detail(page, base_url):
    """Fill target price on deal detail page and submit adds a price alert."""
    page.goto(base_url + "/deals/pepper%3A99999")
    page.wait_for_selector("text=Test Carbon Bike XL")

    # Fill the target price input and click the Target button
    target_input = page.locator("input[name='target_price']")
    target_input.fill("7000")
    page.locator("button:has-text('Target')").click()

    # HTMX swaps the form with a confirmation snippet
    page.wait_for_selector("text=Target set")
    assert "Target set" in page.content()


def test_alerts_page_shows_added_deal(page, base_url):
    """After adding a deal via the Target form, it appears on the alerts page."""
    # First add the deal via the deal detail page
    page.goto(base_url + "/deals/pepper%3A99999")
    page.wait_for_selector("input[name='target_price']")
    page.locator("input[name='target_price']").fill("7000")
    page.locator("button:has-text('Target')").click()
    page.wait_for_selector("text=Target set")

    # Navigate to alerts page
    page.goto(base_url + "/alerts")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Test Carbon Bike XL" in content
    assert "7 000 zl" in content


def test_remove_alert(page, base_url):
    """Clicking Remove button on the alerts page deletes the row via HTMX."""
    # Ensure the deal is on the alerts list first
    page.goto(base_url + "/deals/pepper%3A66666")
    page.wait_for_selector("input[name='target_price']")
    page.locator("input[name='target_price']").fill("4000")
    page.locator("button:has-text('Target')").click()
    page.wait_for_selector("text=Target set")

    # Go to alerts and verify the deal is there
    page.goto(base_url + "/alerts")
    page.wait_for_load_state("networkidle")
    assert "Brand New Road Bike Today" in page.content()

    # Click the Remove button for this row
    row = page.locator("tr", has_text="Brand New Road Bike Today")
    row.locator("button:has-text('Remove')").click()

    # Wait for HTMX to remove the row
    page.wait_for_selector("tr:has-text('Brand New Road Bike Today')", state="detached")
    assert "Brand New Road Bike Today" not in page.content()
