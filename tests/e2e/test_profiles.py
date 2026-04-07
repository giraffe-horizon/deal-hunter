"""E2E tests for profile management pages: list, detail, edit, YAML, create."""

import pytest

pytestmark = pytest.mark.e2e


def test_profiles_list_shows_bikes(page, base_url):
    """The profiles list page contains the 'bikes' profile card."""
    page.goto(base_url + "/profiles")
    content = page.content()
    assert "bikes" in content


def test_profile_detail_shows_budget(page, base_url):
    """The bikes profile detail page displays budget range information."""
    page.goto(base_url + "/profiles/bikes")
    content = page.content()
    assert "Budget" in content
    assert "1 000" in content or "1000" in content  # budget min
    assert "20 000" in content or "20000" in content  # budget max


def test_profile_detail_shows_score_rules(page, base_url):
    """The bikes profile detail page lists score rules (carbon, shimano, 105)."""
    page.goto(base_url + "/profiles/bikes")
    content = page.content()
    assert "Score Rules" in content
    assert "carbon" in content
    assert "shimano" in content


def test_profile_detail_shows_sources(page, base_url):
    """The bikes profile detail page shows configured sources."""
    page.goto(base_url + "/profiles/bikes")
    content = page.content()
    assert "Sources" in content
    assert "pepper" in content


def test_profile_edit_has_form_fields(page, base_url):
    """The profile edit page contains budget and scoring form fields."""
    page.goto(base_url + "/profiles/bikes/edit")

    assert page.locator("#field-budget-min").is_visible()
    assert page.locator("#field-budget-max").is_visible()
    assert page.locator("#field-score-threshold").is_visible()
    assert page.locator("#field-score-alert").is_visible()
    assert page.locator("#field-emoji").is_visible()


def test_profile_yaml_editor_shows_content(page, base_url):
    """The YAML editor page contains the raw YAML with budget and score_rules."""
    page.goto(base_url + "/profiles/bikes/edit/yaml")
    content = page.content()
    assert "budget" in content
    assert "score_rules" in content


def test_profile_create_form_has_required_fields(page, base_url):
    """The profile create page has name, budget, and score threshold fields."""
    page.goto(base_url + "/profiles/new")

    assert page.locator("#field-name").is_visible()
    assert page.locator("#field-budget-min").is_visible()
    assert page.locator("#field-budget-max").is_visible()
    assert page.locator("#field-score-threshold").is_visible()


def test_profile_detail_has_delete_button(page, base_url):
    """The profile detail page has a Delete button."""
    page.goto(base_url + "/profiles/bikes")
    delete_btn = page.get_by_role("button", name="Delete")
    assert delete_btn.is_visible()


def test_create_profile_via_form(page, base_url):
    """Create a throwaway profile via the create form and verify redirect."""
    page.goto(base_url + "/profiles/new")

    page.fill("#field-name", "e2etest")
    page.fill("#field-budget-min", "100")
    page.fill("#field-budget-max", "5000")
    page.fill("#field-score-threshold", "30")

    # Enable at least one source checkbox (pepper should be available)
    pepper_checkbox = page.locator("input[name='source_pepper']")
    if pepper_checkbox.count() > 0:
        pepper_checkbox.check()
        url_input = page.locator("input[name='source_pepper_url']")
        if url_input.is_visible():
            url_input.fill("https://pepper.pl/search?q=test")

    # Submit the form — JS fetch to /api/profiles, then redirects
    page.get_by_role("button", name="Create Profile").click()

    # Wait for navigation to the new profile's detail page
    page.wait_for_url("**/profiles/e2etest", timeout=5000)
    assert "/profiles/e2etest" in page.url

    # Clean up: delete the profile via API
    page.request.delete(
        base_url + "/api/profiles/e2etest",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
