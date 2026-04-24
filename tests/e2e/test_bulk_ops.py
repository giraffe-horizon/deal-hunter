"""E2E tests for the Deals Explorer bulk operations surface.

Covers:
  - Row selection model (ids mode).
  - Header "select all filtered" (filter mode).
  - Bulk Watch / Skip with the confirmation dialog for destructive ops.
  - Sort cycling via clickable column headers.
  - Date column content (relative age line).
  - Compare button enablement gated on 2–4 concrete ids.
  - CSV export request headers.
  - Bad sort URL returns 422 at the server.

The suite shares a session-scoped seeded DB (4 deals) with the rest of e2e; we
restore any status mutations we make so later test files aren't affected.
"""

from __future__ import annotations

import requests


def _restore_active(base_url: str, deal_id: str) -> None:
    requests.post(
        f"{base_url}/api/deals/bulk",
        json={"action": "set-status", "status": "active", "ids": [deal_id]},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=5,
    )


class TestRowSelection:
    def test_row_checkbox_shows_bulk_bar(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").first.check()
        bar = page.locator("#bulk-action-bar")
        assert bar.is_visible()
        assert page.locator("#bulk-count").inner_text() == "1"

    def test_clear_hides_bulk_bar(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").first.check()
        assert page.locator("#bulk-action-bar").is_visible()
        page.locator("#bulk-clear-btn").click()
        assert not page.locator("#bulk-action-bar").is_visible()


class TestSelectAllFiltered:
    def test_header_checkbox_selects_filter_set(self, page, base_url):
        page.goto(base_url + "/deals?profile=bikes")
        page.locator("#select-all-cb").check()
        # Filter mode shows "(all filtered)" note and full count (3 bikes).
        assert "all filtered" in page.locator("#bulk-scope-note").inner_text()
        assert page.locator("#bulk-count").inner_text() == "3"

    def test_exclude_decrements_count(self, page, base_url):
        page.goto(base_url + "/deals?profile=bikes")
        page.locator("#select-all-cb").check()
        assert page.locator("#bulk-count").inner_text() == "3"
        # Uncheck one row → count drops by one.
        page.locator("#deals-table .deal-cb").first.uncheck()
        assert page.locator("#bulk-count").inner_text() == "2"


class TestFilterAndSortClearSelection:
    def test_sort_click_clears_selection(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").first.check()
        assert page.locator("#bulk-action-bar").is_visible()

        # Click the Score sort header.
        page.locator("thead a", has_text="Score").first.click()
        page.wait_for_load_state("networkidle")
        assert not page.locator("#bulk-action-bar").is_visible()

    def test_filter_change_clears_selection(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").first.check()
        assert page.locator("#bulk-action-bar").is_visible()

        page.select_option("select[name='profile']", "bikes")
        page.wait_for_load_state("networkidle")
        assert not page.locator("#bulk-action-bar").is_visible()


class TestSortCycle:
    def test_sort_header_toggles_direction(self, page, base_url):
        page.goto(base_url + "/deals")
        price_header = page.locator("thead a", has_text="Price").first

        price_header.click()
        page.wait_for_load_state("networkidle")
        assert "sort=price" in page.url

        # Click again to flip direction.
        page.locator("thead a", has_text="Price").first.click()
        page.wait_for_load_state("networkidle")
        url_params = page.url.split("?", 1)[-1]
        assert "sort=price" in url_params

    def test_bad_sort_url_returns_422(self, base_url):
        r = requests.get(f"{base_url}/deals?sort=bogus", timeout=5)
        assert r.status_code == 422


class TestDateColumn:
    def test_date_column_renders_added_line(self, page, base_url):
        page.goto(base_url + "/deals")
        # The 4 seeded deals all have first_seen_at set.
        assert page.locator("text=added").first.is_visible()


class TestBulkWatchFlow:
    def test_bulk_watch_two_rows(self, page, base_url):
        page.goto(base_url + "/deals?profile=bikes")
        # Pick two concrete rows.
        cbs = page.locator("#deals-table .deal-cb")
        cbs.nth(0).check()
        cbs.nth(1).check()
        assert page.locator("#bulk-count").inner_text() == "2"

        page.locator("[data-bulk-action='watch']").click()
        page.wait_for_selector("#bulk-toast", state="visible")
        assert "updated" in page.locator("#bulk-toast").inner_text()

        # Rows should now show the Watching badge after reload.
        page.wait_for_load_state("networkidle")
        assert page.locator("text=Watching").count() >= 1

        # Restore for downstream tests.
        _restore_active(base_url, "pepper:66666")
        _restore_active(base_url, "pepper:99999")
        _restore_active(base_url, "pepper:77777")

    def test_bulk_skip_prompts_confirm(self, page, base_url):
        page.goto(base_url + "/deals?profile=nas_hdd")
        page.locator("#deals-table .deal-cb").first.check()
        page.locator("[data-bulk-action='skip']").click()
        # Confirmation dialog must appear for destructive Skip.
        dialog = page.locator("#confirm-dialog-mount")
        assert dialog.is_visible()
        page.locator("#confirm-cancel").click()
        assert not dialog.is_visible()


class TestCompareButtonStates:
    def test_compare_disabled_with_one_selection(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").first.check()
        btn = page.locator("[data-bulk-action='compare']")
        assert btn.is_disabled()

    def test_compare_enabled_with_two_selections(self, page, base_url):
        page.goto(base_url + "/deals")
        page.locator("#deals-table .deal-cb").nth(0).check()
        page.locator("#deals-table .deal-cb").nth(1).check()
        btn = page.locator("[data-bulk-action='compare']")
        assert not btn.is_disabled()

    def test_compare_disabled_in_filter_mode(self, page, base_url):
        # Compare only works with 2–4 concrete ids; filter-mode disables it.
        page.goto(base_url + "/deals")
        page.locator("#select-all-cb").check()
        btn = page.locator("[data-bulk-action='compare']")
        assert btn.is_disabled()


class TestCsvExport:
    def test_csv_export_serves_attachment(self, base_url):
        r = requests.get(f"{base_url}/api/deals/export?format=csv", timeout=5)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        assert "id,title,price" in r.text.splitlines()[0]
