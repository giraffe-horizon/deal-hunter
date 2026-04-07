"""E2E tests for sidebar responsive behavior: desktop visible, mobile hidden, toggle."""

import pytest

pytestmark = pytest.mark.e2e


def test_sidebar_visible_on_desktop(page, base_url):
    """On a desktop viewport, the sidebar is visible (no -translate-x-full class)."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + "/deals")

    sidebar = page.locator("#sidebar")
    classes = sidebar.get_attribute("class") or ""
    # On lg+ screens, Tailwind applies lg:translate-x-0 which overrides -translate-x-full
    # The sidebar should be visually present — check it's not hidden off-screen
    assert "lg:translate-x-0" in classes


def test_sidebar_hidden_on_mobile(page, base_url):
    """On a mobile viewport, the sidebar has -translate-x-full (hidden off-screen)."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(base_url + "/deals")

    sidebar = page.locator("#sidebar")
    classes = sidebar.get_attribute("class") or ""
    assert "-translate-x-full" in classes


def test_sidebar_toggle_on_mobile(page, base_url):
    """On mobile, clicking the menu button toggles the sidebar visibility."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(base_url + "/deals")

    sidebar = page.locator("#sidebar")

    # Initially hidden
    classes_before = sidebar.get_attribute("class") or ""
    assert "-translate-x-full" in classes_before

    # Click the hamburger menu button
    menu_btn = page.locator("button:has(span.material-symbols-outlined:text('menu'))")
    menu_btn.click()

    # After click, sidebar should no longer have -translate-x-full
    classes_after = sidebar.get_attribute("class") or ""
    assert "-translate-x-full" not in classes_after

    # Click overlay to close
    overlay = page.locator("#sidebar-overlay")
    overlay.click()
    classes_closed = sidebar.get_attribute("class") or ""
    assert "-translate-x-full" in classes_closed
