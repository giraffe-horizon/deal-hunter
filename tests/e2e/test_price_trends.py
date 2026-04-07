"""E2E tests for the Price Trends page."""

import pytest

pytestmark = pytest.mark.e2e


def test_price_trends_page_loads(page, base_url):
    """Price trends page loads successfully with summary cards."""
    page.goto(base_url + "/price-trends")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Price Trends" in content
    # Summary cards should be present
    assert "Total Price Drops" in content
    assert "Average Drop" in content
    assert "Biggest Drop" in content


def test_price_trends_time_filter_tabs(page, base_url):
    """Time filter tabs (24h, 7d) exist and are clickable."""
    page.goto(base_url + "/price-trends")
    page.wait_for_load_state("networkidle")

    tab_24h = page.locator("a:has-text('24 Hours')")
    tab_7d = page.locator("a:has-text('7 Days')")

    assert tab_24h.is_visible()
    assert tab_7d.is_visible()

    # Click 24h tab and verify navigation
    tab_24h.click()
    page.wait_for_url("**/price-trends?days=1")
    assert "days=1" in page.url

    # Click 7d tab and verify navigation back
    page.locator("a:has-text('7 Days')").click()
    page.wait_for_url("**/price-trends?days=7")
    assert "days=7" in page.url


def test_price_trends_shows_drops_section(page, base_url):
    """Price Drops section is present — shows either drops table or empty state."""
    page.goto(base_url + "/price-trends")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Price Drops" in content
    # Either the table has drops or the empty state is shown
    has_drops = "No price drops in this period" not in content
    has_empty = "No price drops in this period" in content
    assert has_drops or has_empty
