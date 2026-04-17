"""E2E tests for the Price Drops view (legacy /price-trends redirects here)."""

import pytest

pytestmark = pytest.mark.e2e


def test_price_trends_redirects_to_drops(page, base_url):
    """Legacy /price-trends redirects to /deals?view=drops."""
    page.goto(base_url + "/price-trends")
    page.wait_for_load_state("networkidle")
    assert "view=drops" in page.url


def test_price_drops_view_summary_cards(page, base_url):
    """Price Drops view shows three summary cards."""
    page.goto(base_url + "/deals?view=drops")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Total Price Drops" in content
    assert "Average Drop" in content
    assert "Biggest Drop" in content


def test_price_drops_time_filter_tabs(page, base_url):
    """Time filter tabs (24 Hours, 7 Days) exist and switch the days param."""
    page.goto(base_url + "/deals?view=drops&days=7")
    page.wait_for_load_state("networkidle")

    tab_24h = page.locator("a:has-text('24 Hours')").first
    tab_7d = page.locator("a:has-text('7 Days')").first
    assert tab_24h.is_visible()
    assert tab_7d.is_visible()

    tab_24h.click()
    page.wait_for_url("**/deals?view=drops&days=1")
    assert "days=1" in page.url

    page.locator("a:has-text('7 Days')").first.click()
    page.wait_for_url("**/deals?view=drops&days=7")
    assert "days=7" in page.url


def test_price_drops_table_or_empty(page, base_url):
    """Price Drops section shows either a table or an empty message."""
    page.goto(base_url + "/deals?view=drops")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Price Drops" in content
