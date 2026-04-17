"""Tests for CSRF protection middleware."""

from starlette.testclient import TestClient


def test_post_without_csrf_header_rejected(raw_client: TestClient):
    """POST without HX-Request or X-Requested-With must return 403."""
    resp = raw_client.post(
        "/api/alerts",
        data={"deal_id": "pepper:99999", "target_price": "100"},
        headers={},  # no CSRF headers
    )
    assert resp.status_code == 403


def test_post_with_hx_request_allowed(raw_client: TestClient):
    """POST with HX-Request header must be allowed."""
    resp = raw_client.post(
        "/api/alerts",
        data={"deal_id": "pepper:99999", "target_price": "100"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200


def test_post_with_x_requested_with_allowed(raw_client: TestClient):
    """POST with X-Requested-With header must be allowed."""
    resp = raw_client.post(
        "/api/alerts",
        data={"deal_id": "pepper:99999", "target_price": "100"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200


def test_get_without_csrf_header_allowed(raw_client: TestClient):
    """GET requests must not require CSRF headers."""
    resp = raw_client.get("/deals")
    assert resp.status_code == 200


def test_delete_without_csrf_header_rejected(raw_client: TestClient):
    """DELETE without CSRF headers must return 403."""
    resp = raw_client.delete("/api/alerts/pepper:99999", headers={})
    assert resp.status_code == 403


def test_put_with_x_requested_with_allowed(raw_client: TestClient):
    """PUT with X-Requested-With should be allowed (not blocked by CSRF)."""
    resp = raw_client.put(
        "/api/profiles/nonexistent/yaml",
        content="name: test",
        headers={"Content-Type": "application/octet-stream", "X-Requested-With": "XMLHttpRequest"},
    )
    # 400 or 404, not 403
    assert resp.status_code != 403
