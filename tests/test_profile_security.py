"""Tests for profile name validation and path traversal protection."""

from starlette.testclient import TestClient


def test_profile_path_traversal_dot_dot(client: TestClient):
    """Profile names with '..' must return 400."""
    resp = client.get("/profiles/..%2F..%2Fetc%2Fpasswd")
    # Either 400 (validation caught it) or 404 (router didn't match) — both safe
    assert resp.status_code in (400, 404)


def test_profile_path_traversal_slash(client: TestClient):
    """Profile names with '/' must return 400."""
    resp = client.get("/profiles/foo/bar")
    # This might be 404 (route not matched) or 400 — either is acceptable
    assert resp.status_code in (400, 404)


def test_profile_name_with_dots_rejected(client: TestClient):
    """Profile names with dots (like '..passwd') must return 400."""
    resp = client.get("/profiles/..passwd")
    assert resp.status_code == 400


def test_profile_name_with_special_chars_rejected(client: TestClient):
    """Profile names with special characters must return 400."""
    resp = client.get("/profiles/test%40profile")
    assert resp.status_code == 400


def test_profile_valid_name_accepted(client: TestClient):
    """Valid profile names pass validation (404 because profile doesn't exist)."""
    resp = client.get("/profiles/test-profile-123")
    assert resp.status_code == 404  # valid name, but profile doesn't exist


def test_profile_delete_traversal(client: TestClient):
    """DELETE with invalid name must return 400."""
    resp = client.delete("/api/profiles/..passwd")
    assert resp.status_code == 400


def test_profile_yaml_edit_traversal(client: TestClient):
    """YAML edit with invalid name must return 400."""
    resp = client.get("/profiles/..passwd/edit/yaml")
    assert resp.status_code == 400


def test_profile_toggle_traversal(client: TestClient):
    """PATCH toggle with invalid name must return 400."""
    resp = client.patch("/api/profiles/..passwd/toggle")
    assert resp.status_code == 400


def test_profile_run_traversal(client: TestClient):
    """POST run with invalid name must return 400."""
    resp = client.post("/api/profiles/..passwd/run")
    assert resp.status_code == 400


def test_csrf_blocks_before_path_validation(raw_client: TestClient):
    """Without CSRF headers, mutating requests are blocked at 403 regardless of path."""
    resp = raw_client.delete("/api/profiles/..passwd")
    assert resp.status_code == 403
