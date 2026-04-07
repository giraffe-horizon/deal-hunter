"""E2E tests for CSRF protection: mutating requests require HX-Request or X-Requested-With."""

import pytest

pytestmark = pytest.mark.e2e


def test_post_without_csrf_header_returns_403(page, base_url):
    """POST request without CSRF header is rejected with 403."""
    response = page.request.post(
        base_url + "/api/deals/pepper%3A99999/status",
        form={"status": "watching"},
    )
    assert response.status == 403


def test_delete_without_csrf_header_returns_403(page, base_url):
    """DELETE request without CSRF header is rejected with 403."""
    response = page.request.delete(
        base_url + "/api/watchlist/pepper%3A99999",
    )
    assert response.status == 403


def test_put_without_csrf_header_returns_403(page, base_url):
    """PUT request without CSRF header is rejected with 403."""
    response = page.request.put(
        base_url + "/api/profiles/bikes",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 403


def test_post_with_x_requested_with_header_allowed(page, base_url):
    """POST with X-Requested-With header passes CSRF check (not 403)."""
    response = page.request.post(
        base_url + "/api/deals/pepper%3A99999/status",
        form={"status": "watching"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    # Should not be 403 — may be 200 or 422 depending on payload, but not CSRF blocked
    assert response.status != 403


def test_get_requests_work_without_csrf(page, base_url):
    """GET requests are not subject to CSRF checks."""
    response = page.request.get(base_url + "/deals")
    assert response.status == 200
