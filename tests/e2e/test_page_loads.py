"""Smoke tests: every page loads and renders key elements."""

import pytest

pytestmark = pytest.mark.e2e

PAGES = [
    ("/deals", "Deals Explorer"),
    ("/watchlist", "Watchlist"),
    ("/alerts", "Price Alerts"),
    ("/health", "System Health"),
    ("/profiles", "Profiles"),
    ("/profiles/new", "New Profile"),
    ("/tuner", "Scoring Tuner"),
    ("/compare", "Compare"),
]


@pytest.mark.parametrize("path,expected_text", PAGES)
def test_page_loads(page, base_url, path, expected_text):
    """Each page returns 200 and contains its expected heading text."""
    response = page.goto(base_url + path)
    assert response.status == 200
    assert page.title()
    assert expected_text in page.content()


def test_root_redirects_to_deals(page, base_url):
    """Root path redirects to /deals."""
    page.goto(base_url + "/")
    page.wait_for_url("**/deals")
    assert "/deals" in page.url


def test_deal_detail_loads(page, base_url):
    """Deal detail page renders the deal title."""
    page.goto(base_url + "/deals/pepper%3A99999")
    page.wait_for_selector("text=Test Carbon Bike XL")
    assert "Test Carbon Bike XL" in page.content()


def test_deal_detail_404_for_unknown(page, base_url):
    """Deal detail page returns 404 for a non-existent deal."""
    response = page.goto(base_url + "/deals/nonexistent%3A00000")
    assert response.status == 404


def test_profile_detail_loads(page, base_url):
    """Profile detail page renders the profile name."""
    page.goto(base_url + "/profiles/bikes")
    page.wait_for_selector("text=bikes")
    assert "bikes" in page.content()


def test_tuner_profile_loads(page, base_url):
    """/tuner/<name> redirects to profile page with Tuner tab active."""
    page.goto(base_url + "/tuner/bikes")
    page.wait_for_load_state("networkidle")
    assert "tab=tuner" in page.url
    content = page.content()
    assert "Tuner" in content
    assert "bikes" in content


def test_deals_page_has_title(page, base_url):
    """Deals page has a proper HTML title."""
    page.goto(base_url + "/deals")
    assert "DealMonitor" in page.title()


def test_static_assets_load(page, base_url):
    """Static JS files are served correctly."""
    response = page.goto(base_url + "/static/js/bulk_actions.js")
    assert response.status == 200
