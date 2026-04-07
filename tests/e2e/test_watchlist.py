"""E2E tests for the Watchlist page."""

import pytest

pytestmark = pytest.mark.e2e


def test_empty_watchlist_shows_empty_state(page, base_url):
    """Watchlist page with no items shows an empty state message."""
    page.goto(base_url + "/watchlist")
    page.wait_for_load_state("networkidle")
    assert "No watchlist items" in page.content()


def test_add_to_watchlist_from_deal_detail(page, base_url):
    """Fill target price on deal detail page and submit adds to watchlist."""
    page.goto(base_url + "/deals/pepper%3A99999")
    page.wait_for_selector("text=Test Carbon Bike XL")

    # Fill the target price input and click the Target button
    target_input = page.locator("input[name='target_price']")
    target_input.fill("7000")
    page.locator("button:has-text('Target')").click()

    # HTMX swaps the form with a confirmation snippet
    page.wait_for_selector("text=Target set")
    assert "Target set" in page.content()


def test_watchlist_page_shows_added_deal(page, base_url):
    """After adding a deal to watchlist, it appears on the watchlist page."""
    # First add the deal via the deal detail page
    page.goto(base_url + "/deals/pepper%3A99999")
    page.wait_for_selector("input[name='target_price']")
    page.locator("input[name='target_price']").fill("7000")
    page.locator("button:has-text('Target')").click()
    page.wait_for_selector("text=Target set")

    # Navigate to watchlist page
    page.goto(base_url + "/watchlist")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Test Carbon Bike XL" in content
    assert "7 000 zl" in content


def test_remove_from_watchlist(page, base_url):
    """Clicking Remove button on watchlist deletes the row via HTMX."""
    # Ensure the deal is on the watchlist first
    page.goto(base_url + "/deals/pepper%3A66666")
    page.wait_for_selector("input[name='target_price']")
    page.locator("input[name='target_price']").fill("4000")
    page.locator("button:has-text('Target')").click()
    page.wait_for_selector("text=Target set")

    # Go to watchlist and verify the deal is there
    page.goto(base_url + "/watchlist")
    page.wait_for_load_state("networkidle")
    assert "Brand New Road Bike Today" in page.content()

    # Click the Remove button for this row
    row = page.locator("tr", has_text="Brand New Road Bike Today")
    row.locator("button:has-text('Remove')").click()

    # Wait for HTMX to remove the row
    page.wait_for_selector("tr:has-text('Brand New Road Bike Today')", state="detached")
    assert "Brand New Road Bike Today" not in page.content()
