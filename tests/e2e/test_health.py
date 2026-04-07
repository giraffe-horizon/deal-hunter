"""E2E tests for the Health page."""

import pytest

pytestmark = pytest.mark.e2e


def test_health_page_loads_with_status(page, base_url):
    """Health page loads and displays the operational heartbeat section."""
    page.goto(base_url + "/health")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "System Health" in content
    assert "Operational Heartbeat" in content
    # The seeded health data has status "partial"
    assert "PARTIAL" in content


def test_health_page_shows_profile_results(page, base_url):
    """Health page displays the Profile Results section with bikes profile."""
    page.goto(base_url + "/health")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Profile Results" in content
    assert "bikes" in content
    # Seeded data: bikes profile found 15 deals
    assert "15" in content


def test_health_page_shows_source_status(page, base_url):
    """Health page displays the Source Status Monitor with pepper source."""
    page.goto(base_url + "/health")
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Source Status Monitor" in content
    assert "pepper" in content
