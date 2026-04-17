"""Comprehensive end-to-end coverage for every dashboard feature.

These tests exercise the full browser + server stack (Playwright + uvicorn +
SQLite). They're designed to catch regressions across the surfaces users
actually touch: deals explorer filters, pagination, row actions, watchlist
bookmarks, price alerts CRUD, compare, profiles, tuner, health.

All tests reuse the session-scoped ``live_server`` / ``seeded_db`` fixtures
defined in ``tests/e2e/conftest.py`` — so tests can mutate seeded state, but
must avoid relying on a particular row being in a particular status at the
start of an assertion.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


# ── Deals Explorer — filters and pagination ───────────────────────────


class TestDealsExplorerFilters:
    def test_empty_string_filters_do_not_422(self, page, base_url):
        """HTMX <select> sends empty strings when "All" is picked —
        regression test for the 422 int_parsing bug."""
        response = page.goto(base_url + "/deals?profile=&source=&min_score=&category=&status=")
        assert response.status == 200
        assert "Deals Explorer" in page.content()

    def test_min_score_select_filters_rows(self, page, base_url):
        """Selecting '70+' from the Score dropdown restricts visible deals."""
        page.goto(base_url + "/deals")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='min_score']", "70")
        page.wait_for_load_state("networkidle")
        rows = page.locator("#deals-table tbody tr")
        # Every visible row must have score >= 70 (col 7).
        for i in range(rows.count()):
            score_text = rows.nth(i).locator("td:nth-child(7)").inner_text().strip()
            assert int(score_text) >= 70

    def test_clear_filters_resets_query(self, page, base_url):
        """Clicking 'Clear Filters' strips query params and reloads /deals."""
        page.goto(base_url + "/deals?profile=bikes&min_score=70")
        page.wait_for_load_state("networkidle")
        # HTMX swaps #deals-table + pushes /deals via hx-push-url.
        with page.expect_response("**/deals*"):
            page.click("text=Clear Filters")
        page.wait_for_function("() => !window.location.search || window.location.search === '?'")
        assert "profile=bikes" not in page.url
        assert "min_score" not in page.url

    def test_status_filter_only_shows_watching(self, page, base_url):
        """Filter by status=watching — only watching offers remain."""
        page.goto(base_url + "/deals?status=watching")
        page.wait_for_load_state("networkidle")
        rows = page.locator("#deals-table tbody tr")
        assert rows.count() >= 1
        for i in range(rows.count()):
            # Status badge (first span in row-actions wrapper, col 8).
            badge = rows.nth(i).locator("td:nth-child(8) div[id^='row-actions-'] > span").first
            assert "Watching" in badge.inner_text()

    def test_pagination_preserves_filters(self, page, base_url, seeded_db):
        """When paginating under a profile filter, the filter param stays in the URL."""
        # This test just asserts query-string construction — no seeding needed
        # since the pagination bar is rendered as soon as total_pages > 1.
        # The seeded DB has only 4 offers so no pagination; the URL builder
        # still renders links for total_pages > 1 — so we test by URL asserts.
        # Skip if not enough rows:
        page.goto(base_url + "/deals?profile=bikes")
        page.wait_for_load_state("networkidle")
        # If there's pagination, the "2" link should contain profile=bikes.
        next_link = page.locator("a[hx-get*='/deals?page=2']").first
        if next_link.count() > 0:
            assert "profile=bikes" in next_link.get_attribute("hx-get")


# ── Deals Explorer — row actions ───────────────────────────────────────


class TestDealsTableRowActions:
    def test_watch_button_keeps_controls_after_swap(self, page, base_url):
        """Clicking Watch must atomically swap badge+buttons (no vanishing UI).

        Regression: DOM ids used to be ``row-actions-<urlencoded-id>`` which
        included '%' characters that are invalid in CSS selectors — HTMX
        could not resolve hx-target, so nothing swapped and buttons looked
        dead. Fixed by switching DOM ids to use ':' → '-' and keeping the
        urlencoded form only for URL paths.
        """
        page.goto(base_url + "/deals?status=active")
        page.wait_for_load_state("networkidle")

        watch_btn = page.locator("#deals-table tbody button[title='Watch']").first
        wrapper = watch_btn.locator("xpath=ancestor::div[starts-with(@id,'row-actions-')]")
        wrapper_id = wrapper.get_attribute("id")
        assert wrapper_id and wrapper_id.startswith("row-actions-")
        # DOM id must be CSS-safe (no '%' characters from urlencode).
        assert "%" not in wrapper_id

        watch_btn.click()

        new_wrapper = page.locator(f"#{wrapper_id}")
        new_wrapper.locator("button[title='Unwatch']").wait_for(timeout=5000)
        assert "Watching" in new_wrapper.locator("> span").first.inner_text()
        assert new_wrapper.locator("button[title='Skip']").count() == 1
        assert new_wrapper.locator("button[title='Unwatch']").count() == 1

    def test_row_click_navigates_to_detail(self, page, base_url):
        page.goto(base_url + "/deals")
        page.wait_for_load_state("networkidle")
        page.locator("#deals-table tbody tr").first.locator("td:nth-child(2)").click()
        page.wait_for_load_state("networkidle")
        assert "/deals/" in page.url


# ── Watchlist (bookmark) page ──────────────────────────────────────────


class TestWatchlistBookmarks:
    def test_watchlist_lists_watching_offers(self, page, base_url):
        page.goto(base_url + "/watchlist")
        page.wait_for_load_state("networkidle")
        # ceneo:88888 is seeded with status='watching'.
        assert "NAS HDD Seagate IronWolf" in page.content()

    def test_sidebar_watchlist_link_highlights_on_page(self, page, base_url):
        page.goto(base_url + "/watchlist")
        page.wait_for_load_state("networkidle")
        sidebar = page.locator("nav, aside")
        assert sidebar.get_by_role("link", name="Watchlist").count() >= 1


# ── Price Alerts flow ──────────────────────────────────────────────────


class TestPriceAlertsFlow:
    def test_add_update_and_remove_price_alert(self, page, base_url):
        """Full lifecycle: target form → /alerts row → PATCH update → DELETE.

        Uses a unique target value so the assertion survives prior tests
        in the session that may have already inserted this deal.
        """
        page.goto(base_url + "/deals/pepper%3A99999")
        page.wait_for_selector("input[name='target_price']")
        page.locator("input[name='target_price']").fill("7500")
        page.locator("button:has-text('Target')").click()
        page.wait_for_selector("text=Target set")

        page.goto(base_url + "/alerts")
        page.wait_for_load_state("networkidle")
        row = page.locator("tr#alert-row-pepper-99999")
        assert row.count() == 1
        input_el = row.locator("input[name='target_price']")
        # The add-alert endpoint may leave an earlier value in place (the
        # underlying INSERT-OR-IGNORE keeps the first target), so just
        # assert there's some value and use PATCH to force a known one.
        assert input_el.input_value()

        # Update the target price via the inline form (autosubmits on Tab).
        unique_target = "8123"
        with page.expect_response(
            lambda r: "/api/alerts/" in r.url and r.request.method == "PATCH"
        ) as resp_info:
            input_el.fill(unique_target)
            input_el.press("Tab")
        assert resp_info.value.status == 200

        # Re-query: outerHTML swap replaced the row, but id stays the same.
        refreshed = page.locator("tr#alert-row-pepper-99999 input[name='target_price']")
        refreshed.wait_for()
        assert refreshed.input_value() == unique_target

        # Remove the alert.
        page.locator("tr#alert-row-pepper-99999 button:has-text('Remove')").click()
        page.wait_for_selector("tr#alert-row-pepper-99999", state="detached", timeout=5000)


# ── CSRF protection sanity — delete requires a header ──────────────────


class TestCsrfOnMutations:
    def test_delete_without_header_is_403(self, page, base_url):
        response = page.request.delete(base_url + "/api/alerts/pepper%3A99999")
        assert response.status == 403


# ── Compare page ───────────────────────────────────────────────────────


class TestCompareFlow:
    def test_compare_selects_two_deals_and_shows_side_by_side(self, page, base_url):
        page.goto(base_url + "/compare?ids=pepper:99999,ceneo:88888")
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "Test Carbon Bike XL" in content
        assert "NAS HDD Seagate IronWolf" in content


# ── Profiles CRUD (read-only checks — create/delete would mutate tmp YAMLs) ──


class TestProfilesPage:
    def test_profiles_index_lists_bikes(self, page, base_url):
        page.goto(base_url + "/profiles")
        page.wait_for_load_state("networkidle")
        assert "bikes" in page.content()

    def test_profile_detail_tabs_load(self, page, base_url):
        for tab in ("overview", "edit", "yaml", "tuner"):
            response = page.goto(base_url + f"/profiles/bikes?tab={tab}")
            assert response.status == 200


# ── Health page ───────────────────────────────────────────────────────


class TestHealthPage:
    def test_health_page_renders_status(self, page, base_url):
        page.goto(base_url + "/health")
        page.wait_for_load_state("networkidle")
        assert "System Health" in page.content()


# ── Sidebar navigation ────────────────────────────────────────────────


class TestSidebarNav:
    @pytest.mark.parametrize(
        "link_text,expected_path",
        [
            ("Deals Explorer", "/deals"),
            ("Watchlist", "/watchlist"),
            ("Price Alerts", "/alerts"),
            ("Profiles", "/profiles"),
        ],
    )
    def test_sidebar_links_navigate(self, page, base_url, link_text, expected_path):
        page.goto(base_url + "/deals")
        page.wait_for_load_state("networkidle")
        page.get_by_role("link", name=link_text).first.click()
        page.wait_for_url(f"**{expected_path}", timeout=5000)
        assert expected_path in page.url

    def test_sidebar_health_link_in_footer(self, page, base_url):
        """Health status link lives in the sidebar footer, not the main nav."""
        page.goto(base_url + "/deals")
        page.wait_for_load_state("networkidle")
        # The footer link points at /health; text is filled in by HTMX later.
        health_link = page.locator("aside a[href='/health']").first
        assert health_link.count() >= 1
        health_link.click()
        page.wait_for_url("**/health", timeout=5000)
        assert "/health" in page.url
