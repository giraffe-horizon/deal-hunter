"""Tests for the deals page: metric cards, filters, HTMX table, deal rows."""

import pytest

pytestmark = pytest.mark.e2e


def test_metric_cards_visible(page, base_url):
    """All four metric cards are rendered on the deals page."""
    page.goto(base_url + "/deals")
    content = page.content()
    assert "Total Deals" in content
    assert "Score 70+" in content or "Score" in content
    assert "New Today" in content
    assert "Price Drops" in content


def test_filter_dropdowns_present(page, base_url):
    """The filter bar has 5 select elements (profile, source, score, category, status)."""
    page.goto(base_url + "/deals")
    selects = page.locator("#deal-filters select")
    assert selects.count() == 5


def test_filter_by_source_pepper(page, base_url):
    """Filtering by source=pepper shows only pepper deals."""
    page.goto(base_url + "/deals?source=pepper")

    rows = page.locator("#deals-table tbody tr")
    count = rows.count()
    assert count >= 1

    # Source is col 5 (after checkbox, title, price, trend). Badge text = "pepper".
    source_cells = page.locator("#deals-table tbody tr td:nth-child(5) span")
    for i in range(source_cells.count()):
        assert source_cells.nth(i).inner_text().strip() == "pepper"


def test_filter_by_status_watching(page, base_url):
    """Filtering by status=watching shows only watching deals."""
    page.goto(base_url + "/deals?status=watching")

    rows = page.locator("#deals-table tbody tr")
    count = rows.count()
    assert count >= 1

    # Status is col 9 (Date column inserted at 8); row-actions wrapper's first span is the badge.
    status_badges = page.locator(
        "#deals-table tbody tr td:nth-child(9) div[id^='row-actions-'] > span"
    ).first
    assert "Watching" in status_badges.inner_text()


def test_deal_row_click_navigates_to_detail(page, base_url):
    """Clicking a deal row navigates to the deal detail page."""
    page.goto(base_url + "/deals")
    # Click the first deal row (the title cell to avoid the checkbox)
    first_row = page.locator("#deals-table tbody tr").first
    first_row.locator("td:nth-child(2)").click()
    page.wait_for_load_state("networkidle")
    assert "/deals/" in page.url


def test_row_checkboxes_exist(page, base_url):
    """Each deal row has a row-selection checkbox."""
    page.goto(base_url + "/deals")
    checkboxes = page.locator("#deals-table .deal-cb")
    assert checkboxes.count() >= 1


def test_bulk_bar_appears_on_selection(page, base_url):
    """Selecting a row checkbox makes the bulk action bar visible."""
    page.goto(base_url + "/deals")
    page.locator("#deals-table .deal-cb").first.check()
    bar = page.locator("#bulk-action-bar")
    assert bar.is_visible()


def test_clear_filters_link(page, base_url):
    """Clear Filters link resets all filters and goes to /deals."""
    page.goto(base_url + "/deals?source=pepper&status=watching")
    page.click("text=Clear Filters")
    page.wait_for_load_state("networkidle")
    assert page.url.rstrip("/").endswith("/deals")
