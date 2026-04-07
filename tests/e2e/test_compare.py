"""E2E tests for the Compare page."""

import pytest

pytestmark = pytest.mark.e2e


def test_empty_compare_page_shows_empty_state(page, base_url):
    """Compare page with no IDs shows an empty state message."""
    page.goto(base_url + "/compare")
    page.wait_for_load_state("networkidle")
    assert "No Deals to Compare" in page.content()


def test_compare_page_with_ids_shows_deal_cards(page, base_url):
    """Compare page with deal IDs renders deal cards for each."""
    page.goto(base_url + "/compare?ids=pepper%3A99999,ceneo%3A88888")
    page.wait_for_load_state("networkidle")
    # Both cards should be rendered in the comparison grid
    content = page.content()
    assert "Test Carbon Bike XL" in content
    assert "NAS HDD Seagate IronWolf 8TB" in content


def test_compare_page_shows_both_titles(page, base_url):
    """Both deal titles are visible as headings on the compare page."""
    page.goto(base_url + "/compare?ids=pepper%3A99999,ceneo%3A88888")
    page.wait_for_selector("text=Test Carbon Bike XL")
    page.wait_for_selector("text=NAS HDD Seagate IronWolf 8TB")
    titles = page.locator("h3").all_text_contents()
    title_text = " ".join(titles)
    assert "Test Carbon Bike XL" in title_text
    assert "NAS HDD Seagate IronWolf 8TB" in title_text


def test_compare_page_has_sparkline_canvases(page, base_url):
    """Compare page renders canvas elements with data-sparkline attributes."""
    page.goto(base_url + "/compare?ids=pepper%3A99999,ceneo%3A88888")
    page.wait_for_load_state("networkidle")
    sparklines = page.locator("canvas[data-sparkline]")
    # pepper:99999 has price history so at least one sparkline canvas exists
    assert sparklines.count() >= 1


def test_compare_page_highlights_best_price_and_score(page, base_url):
    """Compare page shows 'Best price' and 'Highest score' highlights."""
    page.goto(base_url + "/compare?ids=pepper%3A99999,ceneo%3A88888")
    page.wait_for_load_state("networkidle")
    content = page.content()
    # ceneo:88888 at 1200 PLN is cheapest -> "Best price"
    assert "Best price" in content
    # pepper:99999 at score 85 is highest -> "Highest score"
    assert "Highest score" in content
