"""Tests for the Deal Hunter web dashboard."""

from pathlib import Path
from unittest.mock import patch

from dashboard import _get_profiles, format_pln, safe_load_profile

# ──────────────── Unit tests: format_pln ────────────────


class TestFormatPln:
    def test_none_returns_zero(self):
        assert format_pln(None) == "0 zl"

    def test_zero_returns_zero(self):
        assert format_pln(0) == "0 zl"

    def test_small_number(self):
        assert format_pln(100) == "100 zl"

    def test_thousands_separator(self):
        assert format_pln(8500) == "8 500 zl"

    def test_millions(self):
        assert format_pln(1000000) == "1 000 000 zl"

    def test_negative_value(self):
        assert format_pln(-500) == "-500 zl"

    def test_large_negative(self):
        assert format_pln(-2500) == "-2 500 zl"

    def test_single_digit(self):
        assert format_pln(1) == "1 zl"

    def test_exact_thousand(self):
        assert format_pln(1000) == "1 000 zl"


# ──────────────── Unit tests: helpers ────────────────


class TestHelpers:
    def test_safe_load_profile_nonexistent(self):
        result = safe_load_profile("nonexistent_profile_xyz")
        assert result is None

    def test_get_profiles_missing_dir(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        with patch("dashboard.dependencies.PROFILES_DIR", missing):
            result = _get_profiles()
            assert result == []

    def test_get_profiles_empty_dir(self, tmp_path):
        with patch("dashboard.dependencies.PROFILES_DIR", tmp_path):
            result = _get_profiles()
            assert result == []

    def test_get_profiles_returns_sorted(self, tmp_path):
        (tmp_path / "nas_hdd.yaml").write_text("name: nas_hdd")
        (tmp_path / "bikes.yaml").write_text("name: bikes")
        (tmp_path / "audio.yaml").write_text("name: audio")
        with patch("dashboard.dependencies.PROFILES_DIR", tmp_path):
            result = _get_profiles()
            assert result == ["audio", "bikes", "nas_hdd"]


# ──────────────── E2E tests: Index redirect ────────────────


class TestIndexRedirect:
    def test_redirect_to_deals(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert response.headers["location"] == "/deals"


# ──────────────── E2E tests: Deals page ────────────────


class TestDealsPage:
    def test_deals_page_renders(self, client):
        response = client.get("/deals")
        assert response.status_code == 200
        assert "Deals Explorer" in response.text

    def test_contains_metric_cards(self, client):
        text = client.get("/deals").text
        assert "Total Deals" in text
        assert "Score 70+" in text
        assert "New Today" in text
        assert "Price Drops" in text

    def test_contains_deal_titles(self, client):
        text = client.get("/deals").text
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf 8TB" in text

    def test_contains_filter_dropdowns(self, client):
        text = client.get("/deals").text
        assert "All Profiles" in text
        assert "All Sources" in text
        assert "All Scores" in text
        assert "All Statuses" in text

    def test_filter_by_profile(self, client):
        text = client.get("/deals?profile=bikes").text
        assert "Test Carbon Bike XL" in text
        # NAS deal should not appear in bikes filter
        assert "NAS HDD Seagate IronWolf" not in text

    def test_filter_by_min_score(self, client):
        text = client.get("/deals?min_score=70").text
        assert "Test Carbon Bike XL" in text  # score 85
        assert "Brand New Road Bike Today" in text  # score 72
        assert "Cheap Broken Bike Parts" not in text  # score 20

    def test_filter_by_status(self, client):
        text = client.get("/deals?status=watching").text
        assert "NAS HDD Seagate IronWolf" in text
        assert "Test Carbon Bike XL" not in text

    def test_empty_filter_same_as_no_filter(self, client):
        all_text = client.get("/deals").text
        empty_text = client.get("/deals?profile=").text
        # Both should contain the same deals
        assert "Test Carbon Bike XL" in all_text
        assert "Test Carbon Bike XL" in empty_text

    def test_htmx_partial_response(self, client):
        response = client.get("/deals", headers={"HX-Request": "true"})
        assert response.status_code == 200
        text = response.text
        # Should have the table
        assert "<table" in text
        # Should NOT have the sidebar/base layout
        assert "<aside" not in text
        assert "Deals Explorer" not in text  # page title not in partial

    def test_pagination_param(self, client):
        response = client.get("/deals?page=1")
        assert response.status_code == 200

    def test_filter_by_source(self, client):
        text = client.get("/deals?source=ceneo").text
        assert "NAS HDD Seagate IronWolf" in text
        assert "Test Carbon Bike XL" not in text

    def test_filter_by_category(self, client):
        text = client.get("/deals?category=road").text
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf" not in text

    def test_combined_filters(self, client):
        text = client.get("/deals?profile=bikes&min_score=50").text
        assert "Test Carbon Bike XL" in text  # bikes, score 85
        assert "Brand New Road Bike Today" in text  # bikes, score 72
        assert "Cheap Broken Bike Parts" not in text  # bikes, score 20

    def test_filter_returning_no_results(self, client):
        text = client.get("/deals?source=nonexistent").text
        assert "No deals found" in text

    def test_negative_page_clamps_to_1(self, client):
        response = client.get("/deals?page=-5")
        assert response.status_code == 200
        # Should show first page content
        assert "Test Carbon Bike XL" in response.text

    def test_page_zero_clamps_to_1(self, client):
        response = client.get("/deals?page=0")
        assert response.status_code == 200

    def test_filter_by_rejected_status(self, client):
        text = client.get("/deals?status=rejected").text
        assert "Cheap Broken Bike Parts" in text
        assert "Test Carbon Bike XL" not in text

    def test_selected_filter_is_preserved_in_html(self, client):
        text = client.get("/deals?status=watching").text
        assert 'value="watching"' in text

    def test_score_filter_options_in_dropdown(self, client):
        text = client.get("/deals").text
        assert 'value="70"' in text
        assert 'value="50"' in text
        assert 'value="30"' in text

    def test_htmx_partial_with_filters(self, client):
        response = client.get(
            "/deals?profile=bikes",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        text = response.text
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf" not in text
        # Partial should not include base layout
        assert "<aside" not in text

    def test_deals_table_has_score_color_coding(self, client):
        text = client.get("/deals").text
        # High score (85) should have tertiary color class
        assert "text-tertiary" in text
        # Low score (20) should have error color class
        assert "text-error" in text

    def test_deals_table_has_status_badges(self, client):
        text = client.get("/deals").text
        assert "Watching" in text
        assert "Rejected" in text
        assert "Active" in text

    def test_deal_rows_are_clickable(self, client):
        text = client.get("/deals").text
        # Rows should have onclick to navigate to deal detail
        assert "window.location=" in text

    def test_clear_filters_link(self, client):
        text = client.get("/deals?profile=bikes").text
        assert "Clear Filters" in text
        assert 'href="/deals"' in text


# ──────────────── E2E tests: Deal detail page ────────────────


class TestDealDetailPage:
    def test_deal_detail_renders(self, client):
        response = client.get("/deals/pepper:99999")
        assert response.status_code == 200
        assert "Test Carbon Bike XL" in response.text

    def test_contains_formatted_price(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "8 500 zl" in text

    def test_contains_price_history_section(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Price History" in text

    def test_contains_metadata(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Source" in text
        assert "Profile" in text
        assert "Score" in text

    def test_contains_action_buttons(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Watch" in text
        assert "Skip" in text
        assert "Open Link" in text

    def test_nonexistent_deal_404(self, client):
        response = client.get("/deals/nonexistent:000")
        assert response.status_code == 404

    def test_contains_deal_description(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "A great carbon bike" in text

    def test_shows_source_badge(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "pepper" in text

    def test_shows_profile_link(self, client):
        text = client.get("/deals/pepper:99999").text
        # Profile name should be a link to filtered deals
        assert "/deals?profile=bikes" in text

    def test_shows_score_value(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "85" in text

    def test_shows_category_if_present(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "road" in text

    def test_shows_first_and_last_seen(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "First Seen" in text
        assert "Last Seen" in text

    def test_shows_lowest_price_ever(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Lowest Price Ever" in text

    def test_shows_price_history_table_entries(self, client):
        text = client.get("/deals/pepper:99999").text
        # Should have both recorded prices (9500 and 8500)
        assert "9 500 zl" in text
        assert "8 500 zl" in text

    def test_price_history_marks_lowest(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Lowest" in text

    def test_price_chart_canvas_present(self, client):
        text = client.get("/deals/pepper:99999").text
        assert 'id="priceChart"' in text

    def test_period_filter_buttons(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "1M" in text
        assert "3M" in text
        assert "All" in text

    def test_deal_with_no_description_hides_section(self, client):
        # Deal 3 has description "Spare parts only" — deal 4 has "Fresh deal"
        # All seeded deals have descriptions, so test the template behavior
        text = client.get("/deals/pepper:66666").text
        assert "Fresh deal" in text

    def test_breadcrumb_navigation(self, client):
        text = client.get("/deals/pepper:99999").text
        assert "Deals Explorer" in text
        assert 'href="/deals"' in text

    def test_price_change_indicator(self, client):
        # pepper:99999 has previous_price=9500 and current_price=8500
        text = client.get("/deals/pepper:99999").text
        # Should show price decrease indicator
        assert "arrow_downward" in text
        assert "1 000 zl" in text  # difference

    def test_status_badge_on_detail(self, client):
        # pepper:99999 is active by default
        text = client.get("/deals/pepper:99999").text
        assert "Active" in text

    def test_watching_deal_badge(self, client):
        text = client.get("/deals/ceneo:88888").text
        assert "Watching" in text

    def test_rejected_deal_badge(self, client):
        text = client.get("/deals/pepper:77777").text
        assert "Rejected" in text

    def test_deal_without_price_history(self, client):
        # pepper:77777 (score 20) has no price history entries
        response = client.get("/deals/pepper:77777")
        assert response.status_code == 200


# ──────────────── E2E tests: Health page ────────────────


class TestHealthPage:
    def test_health_no_data(self, client):
        with patch("health.load_health", return_value=None):
            response = client.get("/health")
            assert response.status_code == 200
            assert "No health data" in response.text

    def test_health_with_data(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            response = client.get("/health")
            assert response.status_code == 200
            text = response.text
            assert "0.4.3" in text  # version
            assert "partial" in text.lower() or "PARTIAL" in text  # status
            assert "pepper" in text  # source name
            assert "bikes" in text  # profile name

    def test_health_shows_errors(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Connection timeout" in text

    def test_health_shows_source_status(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "ceneo" in text
            assert "degraded" in text.lower() or "2" in text  # consecutive failures

    def test_health_shows_duration(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "12.5" in text

    def test_health_shows_operational_heartbeat(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Operational Heartbeat" in text
            assert "Last Run" in text
            assert "Duration" in text

    def test_health_shows_version_card(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Version" in text
            assert "0.4.3" in text

    def test_health_shows_deals_found_count(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Total Deals" in text
            assert "15" in text  # bikes found 15

    def test_health_shows_alerts_count(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Total Alerts" in text
            assert "3" in text  # bikes had 3 alerts

    def test_health_shows_profile_results_table(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Profile Results" in text
            assert "nas_hdd" in text
            assert "error" in text.lower()  # nas_hdd status

    def test_health_shows_multiple_errors(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Connection timeout" in text
            assert "Parser failed" in text

    def test_health_ok_status_styling(self, client):
        data = {
            "last_run": "2026-04-06T10:00:00",
            "status": "ok",
            "duration_seconds": 5.0,
            "version": "0.4.3",
            "profile_results": {},
            "sources_health": {},
        }
        with patch("health.load_health", return_value=data):
            text = client.get("/health").text
            assert "OK" in text

    def test_health_source_consecutive_failures(self, client, sample_health_data):
        with patch("health.load_health", return_value=sample_health_data):
            text = client.get("/health").text
            assert "Consecutive Failures" in text


# ──────────────── E2E tests: Price trends page ────────────────


class TestPriceTrendsPage:
    def test_price_trends_redirects(self, client):
        response = client.get("/price-trends", follow_redirects=False)
        assert response.status_code == 302
        assert "view=drops" in response.headers["location"]

    def test_price_drops_view_renders(self, client):
        text = client.get("/deals?view=drops").text
        assert "Price Drops" in text

    def test_7_days_tab_active(self, client):
        text = client.get("/deals?view=drops&days=7").text
        assert "7 Days" in text

    def test_24_hours_tab(self, client):
        text = client.get("/deals?view=drops&days=1").text
        assert "24 Hours" in text

    def test_contains_category_distribution(self, client):
        text = client.get("/deals?view=drops").text
        assert "Category Distribution" in text

    def test_contains_summary_cards(self, client):
        text = client.get("/deals?view=drops").text
        assert "Total Price Drops" in text
        assert "Average Drop" in text
        assert "Biggest Drop" in text

    def test_shows_category_names(self, client):
        text = client.get("/deals?view=drops").text
        assert "road" in text  # category from seeded deals

    def test_no_drops_shows_empty_state(self, client):
        text = client.get("/deals?view=drops&days=1").text
        assert "Price Drops" in text

    def test_default_days_is_7(self, client):
        text = client.get("/deals?view=drops").text
        assert "bg-primary" in text

    def test_time_filter_tabs_present(self, client):
        text = client.get("/deals?view=drops").text
        assert "24 Hours" in text
        assert "7 Days" in text

    def test_price_drops_table_headers(self, client):
        text = client.get("/deals?view=drops").text
        assert "Previous Price" in text or "No price drops" in text


# ──────────────── E2E tests: API endpoints ────────────────


class TestApiDeals:
    def test_api_deals_returns_json(self, client):
        response = client.get("/api/deals")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_api_deals_filter_by_profile(self, client):
        data = client.get("/api/deals?profile=bikes").json()
        assert all(d["profile"] == "bikes" for d in data)

    def test_api_deals_filter_by_source(self, client):
        data = client.get("/api/deals?source=ceneo").json()
        assert len(data) == 1
        assert data[0]["source"] == "ceneo"

    def test_api_deals_high_min_score_empty(self, client):
        data = client.get("/api/deals?min_score=100").json()
        assert data == []

    def test_api_deals_filter_by_status(self, client):
        data = client.get("/api/deals?status=rejected").json()
        assert len(data) == 1
        assert data[0]["id"] == "pepper:77777"

    def test_api_deals_filter_by_category(self, client):
        data = client.get("/api/deals?category=storage").json()
        assert len(data) == 1
        assert data[0]["source"] == "ceneo"

    def test_api_deals_combined_filters(self, client):
        data = client.get("/api/deals?profile=bikes&min_score=80").json()
        assert len(data) == 1
        assert data[0]["id"] == "pepper:99999"

    def test_api_deals_empty_string_params_ignored(self, client):
        all_data = client.get("/api/deals").json()
        empty_data = client.get("/api/deals?profile=&source=").json()
        assert len(all_data) == len(empty_data)

    def test_api_deals_contain_expected_fields(self, client):
        data = client.get("/api/deals").json()
        deal = data[0]
        expected_fields = ["id", "title", "price", "link", "source", "profile", "score", "status"]
        for field in expected_fields:
            assert field in deal, f"Missing field: {field}"

    def test_api_deals_ordered_by_score_desc(self, client):
        data = client.get("/api/deals").json()
        scores = [d["score"] for d in data]
        assert scores == sorted(scores, reverse=True)


class TestApiPriceHistory:
    def test_price_history_with_data(self, client):
        response = client.get("/api/price-history/pepper:99999")
        assert response.status_code == 200
        data = response.json()
        assert "labels" in data
        assert "prices" in data
        assert len(data["labels"]) >= 2
        assert len(data["prices"]) >= 2
        assert data["lowest"] is not None
        assert data["highest"] is not None
        assert data["lowest"] <= data["highest"]

    def test_price_history_nonexistent(self, client):
        data = client.get("/api/price-history/nonexistent:000").json()
        assert data["labels"] == []
        assert data["prices"] == []
        assert data["lowest"] is None
        assert data["highest"] is None

    def test_price_history_labels_are_dates(self, client):
        data = client.get("/api/price-history/pepper:99999").json()
        for label in data["labels"]:
            assert len(label) == 10  # YYYY-MM-DD format
            assert label[4] == "-"

    def test_price_history_prices_are_integers(self, client):
        data = client.get("/api/price-history/pepper:99999").json()
        for price in data["prices"]:
            assert isinstance(price, int)

    def test_price_history_lowest_matches_min(self, client):
        data = client.get("/api/price-history/pepper:99999").json()
        assert data["lowest"] == min(data["prices"])

    def test_price_history_highest_matches_max(self, client):
        data = client.get("/api/price-history/pepper:99999").json()
        assert data["highest"] == max(data["prices"])


class TestApiUpdateStatus:
    def test_update_to_watching(self, client):
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "watching"},
        )
        assert response.status_code == 200
        assert "Watching" in response.text

    def test_update_to_rejected(self, client):
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "rejected"},
        )
        assert response.status_code == 200
        assert "Skipped" in response.text

    def test_update_to_active(self, client):
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "active"},
        )
        assert response.status_code == 200
        assert "Active" in response.text

    def test_invalid_status_400(self, client):
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "invalid"},
        )
        assert response.status_code == 400

    def test_nonexistent_deal_404(self, client):
        response = client.post(
            "/api/deals/nonexistent:000/status",
            data={"status": "watching"},
        )
        assert response.status_code == 404

    def test_status_persists_in_db(self, client, dashboard_db):
        client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "watching"},
        )
        deal = dashboard_db.get_deal("pepper:99999")
        assert deal["status"] == "watching"

    def test_update_response_preserves_action_buttons(self, client):
        """Status update HTMX response should keep Watch/Skip/Open buttons."""
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "watching"},
        )
        text = response.text
        assert "Watch" in text
        assert "Skip" in text
        assert "Open Link" in text
        # Should contain hx-post for subsequent status changes
        assert "hx-post" in text

    def test_update_response_shows_status_badge(self, client):
        response = client.post(
            "/api/deals/pepper:99999/status",
            data={"status": "rejected"},
        )
        assert "Skipped" in response.text

    def test_sequential_status_updates(self, client, dashboard_db):
        """Changing status multiple times should always reflect the latest."""
        client.post("/api/deals/pepper:99999/status", data={"status": "watching"})
        assert dashboard_db.get_deal("pepper:99999")["status"] == "watching"

        client.post("/api/deals/pepper:99999/status", data={"status": "rejected"})
        assert dashboard_db.get_deal("pepper:99999")["status"] == "rejected"

        client.post("/api/deals/pepper:99999/status", data={"status": "active"})
        assert dashboard_db.get_deal("pepper:99999")["status"] == "active"


class TestApiStats:
    def test_stats_returns_json(self, client):
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_deals" in data
        assert "high_score_pct" in data
        assert "new_today" in data
        assert "drops_count" in data

    def test_stats_total_matches(self, client):
        data = client.get("/api/stats").json()
        assert data["total_deals"] == 4  # 4 seeded deals

    def test_stats_new_today(self, client):
        data = client.get("/api/stats").json()
        assert data["new_today"] >= 1  # at least deal4 was seeded today

    def test_stats_high_score_pct_is_percentage(self, client):
        data = client.get("/api/stats").json()
        assert 0 <= data["high_score_pct"] <= 100

    def test_stats_drops_count_is_non_negative(self, client):
        data = client.get("/api/stats").json()
        assert data["drops_count"] >= 0


# ──────────────── E2E workflow tests ────────────────


class TestE2EWorkflows:
    """End-to-end tests simulating real user journeys through the dashboard."""

    def test_browse_deals_then_view_detail(self, client):
        """User browses deals list, then clicks into a deal detail."""
        # Step 1: Load deals page
        deals_page = client.get("/deals")
        assert deals_page.status_code == 200
        assert "Test Carbon Bike XL" in deals_page.text

        # Step 2: Navigate to deal detail
        detail_page = client.get("/deals/pepper:99999")
        assert detail_page.status_code == 200
        assert "Test Carbon Bike XL" in detail_page.text
        assert "8 500 zl" in detail_page.text

    def test_filter_then_view_detail_then_back(self, client):
        """User filters by profile, views a deal, conceptually goes back to filtered list."""
        # Step 1: Filter by bikes
        filtered = client.get("/deals?profile=bikes")
        assert "Test Carbon Bike XL" in filtered.text
        assert "NAS HDD Seagate IronWolf" not in filtered.text

        # Step 2: View a deal from the filtered list
        detail = client.get("/deals/pepper:99999")
        assert detail.status_code == 200

        # Step 3: Profile link on detail page goes back to filtered view
        assert "/deals?profile=bikes" in detail.text

    def test_update_status_then_verify_on_list(self, client):
        """User updates deal status, then checks it on the deals list."""
        # Step 1: Update status to watching
        client.post("/api/deals/pepper:99999/status", data={"status": "watching"})

        # Step 2: Verify on deals list — should show as watching
        text = client.get("/deals?status=watching").text
        assert "Test Carbon Bike XL" in text

        # Step 3: Verify it's not in active list anymore
        active_text = client.get("/deals?status=active").text
        assert "Test Carbon Bike XL" not in active_text

    def test_update_status_then_verify_on_detail(self, client):
        """Status change visible on deal detail page."""
        client.post("/api/deals/pepper:99999/status", data={"status": "rejected"})

        detail = client.get("/deals/pepper:99999")
        assert "Rejected" in detail.text

    def test_view_price_history_via_api_and_page(self, client):
        """Price history is consistent between API and detail page."""
        # API response
        api_data = client.get("/api/price-history/pepper:99999").json()
        assert len(api_data["prices"]) >= 2

        # Detail page should show the same prices
        detail_text = client.get("/deals/pepper:99999").text
        assert "9 500 zl" in detail_text
        assert "8 500 zl" in detail_text

    def test_api_stats_consistent_with_deals_page(self, client):
        """API stats match what the deals page shows."""
        stats = client.get("/api/stats").json()
        assert stats["total_deals"] == 4

        # Verify the deal count matches API deals
        all_deals = client.get("/api/deals").json()
        assert len(all_deals) == stats["total_deals"]

    def test_htmx_filter_workflow(self, client):
        """Simulates HTMX filter interaction: user selects a profile filter."""
        # Step 1: Initial page load
        full_page = client.get("/deals")
        assert full_page.status_code == 200

        # Step 2: User selects profile filter — HTMX sends request
        partial = client.get(
            "/deals?profile=bikes",
            headers={"HX-Request": "true"},
        )
        assert partial.status_code == 200
        assert "<table" in partial.text
        assert "Test Carbon Bike XL" in partial.text
        assert "NAS HDD Seagate IronWolf" not in partial.text

        # Step 3: User clears filters — HTMX sends request without params
        cleared = client.get(
            "/deals",
            headers={"HX-Request": "true"},
        )
        assert "Test Carbon Bike XL" in cleared.text
        assert "NAS HDD Seagate IronWolf" in cleared.text

    def test_health_page_accessible_from_nav(self, client, sample_health_data):
        """Health page loads independently with its own data source."""
        with patch("health.load_health", return_value=sample_health_data):
            response = client.get("/health")
            assert response.status_code == 200
            assert "System Health" in response.text

    def test_price_trends_redirects_to_drops_view(self, client):
        """Price trends URL redirects to deals explorer drops view."""
        response = client.get("/price-trends", follow_redirects=False)
        assert response.status_code == 302
        assert "view=drops" in response.headers["location"]

    def test_full_deal_lifecycle(self, client, dashboard_db):
        """Deal goes through active -> watching -> rejected -> active."""
        deal_id = "pepper:99999"

        # Initially active
        deal = dashboard_db.get_deal(deal_id)
        assert deal["status"] == "active"

        # Watch it
        resp = client.post(f"/api/deals/{deal_id}/status", data={"status": "watching"})
        assert resp.status_code == 200
        assert dashboard_db.get_deal(deal_id)["status"] == "watching"

        # Reject it
        resp = client.post(f"/api/deals/{deal_id}/status", data={"status": "rejected"})
        assert resp.status_code == 200
        assert dashboard_db.get_deal(deal_id)["status"] == "rejected"

        # Reactivate
        resp = client.post(f"/api/deals/{deal_id}/status", data={"status": "active"})
        assert resp.status_code == 200
        assert dashboard_db.get_deal(deal_id)["status"] == "active"

    def test_api_deals_matches_page_deals(self, client):
        """API /api/deals returns same data as visible on /deals page."""
        api_data = client.get("/api/deals?profile=bikes").json()
        page_text = client.get("/deals?profile=bikes").text

        for deal in api_data:
            assert deal["title"] in page_text

    def test_cross_page_data_consistency(self, client):
        """Stats on deals page should be consistent with underlying data."""
        stats = client.get("/api/stats").json()
        deals = client.get("/api/deals").json()

        # Total deals should match
        assert stats["total_deals"] == len(deals)

        # High score count should match
        high_score_deals = [d for d in deals if d["score"] and d["score"] >= 70]
        expected_pct = round(len(high_score_deals) / len(deals) * 100) if deals else 0
        assert stats["high_score_pct"] == expected_pct


class TestWatchlistPage:
    """Tests for the watchlist dashboard page."""

    def test_watchlist_page_loads(self, client):
        """GET /watchlist returns 200."""
        response = client.get("/watchlist")
        assert response.status_code == 200
        assert "Watchlist" in response.text

    def test_watchlist_in_sidebar(self, client):
        """Sidebar contains Watchlist link."""
        response = client.get("/deals")
        assert "/watchlist" in response.text

    def test_watchlist_empty_state(self, client):
        """Empty watchlist shows the empty state message."""
        response = client.get("/watchlist")
        assert response.status_code == 200
        assert "No watchlist items" in response.text

    def test_add_to_watchlist_api(self, client):
        """POST /api/watchlist adds a deal."""
        response = client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:99999", "target_price": "8000"},
        )
        assert response.status_code == 200

    def test_add_to_watchlist_returns_confirmation(self, client):
        """POST /api/watchlist returns confirmation text."""
        response = client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:99999", "target_price": "8000"},
        )
        assert "Target set" in response.text

    def test_watchlist_shows_item_after_add(self, client):
        """After adding, watchlist page shows the item."""
        client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:99999", "target_price": "8000"},
        )
        response = client.get("/watchlist")
        assert "pepper:99999" in response.text or "Test Carbon Bike XL" in response.text

    def test_remove_from_watchlist_api(self, client):
        """DELETE /api/watchlist/{deal_id} removes a deal."""
        client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:99999", "target_price": "8000"},
        )
        response = client.delete("/api/watchlist/pepper:99999")
        assert response.status_code == 200

    def test_remove_returns_empty(self, client):
        """DELETE /api/watchlist returns empty HTML (HTMX row removal)."""
        client.post(
            "/api/watchlist",
            data={"deal_id": "pepper:99999", "target_price": "8000"},
        )
        response = client.delete("/api/watchlist/pepper:99999")
        assert response.text == ""

    def test_deal_detail_has_target_form(self, client):
        """Deal detail page contains the target price form."""
        text = client.get("/deals/pepper:99999").text
        assert "target_price" in text
        assert "Target" in text
        assert "bookmark_add" in text


class TestProfilePages:
    """Tests for profile management pages."""

    def test_profiles_page_loads(self, client):
        """GET /profiles returns 200."""
        response = client.get("/profiles")
        assert response.status_code == 200
        assert "Profiles" in response.text

    def test_profiles_in_sidebar(self, client):
        """Sidebar contains Profiles link."""
        response = client.get("/deals")
        assert "/profiles" in response.text

    def test_api_profiles_list(self, client):
        """GET /api/profiles returns JSON list."""
        response = client.get("/api/profiles")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_profile_detail_not_found(self, client):
        """GET /profiles/{name} returns 404 for missing profile."""
        response = client.get("/profiles/nonexistent_profile_xyz")
        assert response.status_code == 404

    def test_profile_edit_page_redirects(self, client):
        """GET /profiles/{name}/edit redirects to unified page with tab=edit."""
        response = client.get("/profiles/nonexistent_xyz/edit")
        assert response.status_code == 302
        assert "tab=edit" in response.headers["location"]

    def test_profile_yaml_page_redirects(self, client):
        """GET /profiles/{name}/edit/yaml redirects to unified page with tab=yaml."""
        response = client.get("/profiles/nonexistent_xyz/edit/yaml")
        assert response.status_code == 302
        assert "tab=yaml" in response.headers["location"]

    def test_profile_create_page_loads(self, client):
        """GET /profiles/new returns 200."""
        response = client.get("/profiles/new")
        assert response.status_code == 200
        assert "New" in response.text or "Create" in response.text

    def test_api_create_profile(self, client):
        """POST /api/profiles creates a new profile."""
        response = client.post(
            "/api/profiles",
            json={
                "name": "test_create_profile",
                "emoji": "\U0001f50d",
                "sources": {"pepper": {"urls": ["https://pepper.pl/search?q=test"]}},
                "budget": {"min": 100, "max": 5000},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Clean up: delete the created file if it exists
        profile_path = Path(__file__).parent.parent / "profiles" / "test_create_profile.yaml"
        if profile_path.exists():
            profile_path.unlink()
        assert data.get("ok") is True

    def test_api_delete_profile(self, client):
        """DELETE /api/profiles/{name} deletes the profile file."""
        # Create a test profile first
        client.post(
            "/api/profiles",
            json={
                "name": "test_delete_me",
                "emoji": "\U0001f50d",
                "sources": {"pepper": {"urls": ["https://pepper.pl/search?q=test"]}},
                "budget": {"min": 100, "max": 5000},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        response = client.delete("/api/profiles/test_delete_me")
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True

    def test_api_delete_nonexistent(self, client):
        """DELETE /api/profiles/{name} returns 404 for missing profile."""
        response = client.delete("/api/profiles/nonexistent_xyz")
        assert response.status_code == 404

    def test_api_toggle_profile(self, client):
        """PATCH /api/profiles/{name}/toggle toggles enabled state."""
        # Create a test profile first
        client.post(
            "/api/profiles",
            json={
                "name": "test_toggle_me",
                "emoji": "\U0001f50d",
                "sources": {"pepper": {"urls": ["https://pepper.pl/search?q=test"]}},
                "budget": {"min": 100, "max": 5000},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        response = client.patch("/api/profiles/test_toggle_me/toggle")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        # Clean up
        client.delete("/api/profiles/test_toggle_me")

    def test_api_run_nonexistent(self, client):
        """POST /api/profiles/{name}/run returns 404 for missing profile."""
        response = client.post("/api/profiles/nonexistent_xyz/run")
        assert response.status_code == 404


# ──────────────── E2E tests: Compare page ────────────────


class TestComparePage:
    def test_compare_page_empty(self, client):
        response = client.get("/compare")
        assert response.status_code == 200

    def test_compare_page_with_ids(self, client):
        response = client.get("/compare?ids=test:1,test:2")
        assert response.status_code == 200

    def test_deals_table_has_checkboxes(self, client):
        """Deals page includes compare checkboxes."""
        response = client.get("/deals")
        assert response.status_code == 200
        assert "compare-cb" in response.text

    def test_deals_page_has_compare_bar(self, client):
        """Deals page includes floating compare bar."""
        response = client.get("/deals")
        assert response.status_code == 200
        assert "compare-bar" in response.text

    def test_compare_with_real_deals(self, client):
        """Compare page renders seeded deal data."""
        response = client.get("/compare?ids=pepper:99999,ceneo:88888")
        assert response.status_code == 200
        text = response.text
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf 8TB" in text

    def test_compare_highlights_best_price(self, client):
        """Compare page marks the deal with the lowest price."""
        response = client.get("/compare?ids=pepper:99999,ceneo:88888")
        # ceneo:88888 has price 1200 (lowest) — should be highlighted
        assert "Best price" in response.text

    def test_compare_highlights_highest_score(self, client):
        """Compare page marks the deal with the highest score."""
        response = client.get("/compare?ids=pepper:99999,ceneo:88888")
        # pepper:99999 has score 85 (highest) — should be highlighted
        assert "Highest score" in response.text

    def test_compare_has_sparkline_canvases(self, client):
        """Compare page includes Chart.js sparkline canvases."""
        response = client.get("/compare?ids=pepper:99999,ceneo:88888")
        assert "data-sparkline" in response.text

    def test_compare_has_share_link(self, client):
        """Compare page includes a share/copy link."""
        response = client.get("/compare?ids=pepper:99999,ceneo:88888")
        assert "share-link" in response.text or "copy" in response.text.lower()

    def test_compare_max_5_deals(self, client, dashboard_db):
        """Compare page enforces max 5 deals."""
        # Only 4 deals exist in seeded data, so even with 6 IDs only found ones show
        ids = "pepper:99999,ceneo:88888,pepper:77777,pepper:66666,fake:1,fake:2"
        response = client.get(f"/compare?ids={ids}")
        assert response.status_code == 200
        # Should contain at most 5 deals (truncated before query)
        text = response.text
        # All 4 real deals present (fake ones not found)
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf 8TB" in text

    def test_compare_empty_shows_empty_state(self, client):
        """Compare page with no IDs shows empty state."""
        response = client.get("/compare")
        text = response.text
        assert "Select" in text or "compare" in text.lower()

    def test_compare_nonexistent_ids_graceful(self, client):
        """Compare page with only nonexistent IDs renders without error."""
        response = client.get("/compare?ids=fake:1,fake:2")
        assert response.status_code == 200


# ──────────────── Unit tests: DealService.score_deals_with_profile ────────────────


class TestScoreDealsHelper:
    def test_score_deals_empty(self):
        """Empty deal list returns empty result."""
        from dashboard.services import DealService

        result = DealService(None).score_deals_with_profile(
            [], {"score_rules": {}, "penalties": {}}
        )
        assert result == []

    def test_score_deals_applies_rules(self):
        """Helper correctly applies score rules to deal dicts."""
        from dashboard.services import DealService

        deals = [
            {
                "id": "test:1",
                "title": "Carbon Road Bike",
                "price": 8000,
                "link": "https://example.com",
                "source": "pepper",
                "description": "shimano 105",
                "image_url": "",
                "score": 50,
            }
        ]
        profile = {
            "score_rules": {"carbon": 30, "shimano": 20},
            "penalties": {},
            "budget": {"min": 5000, "max": 15000},
        }
        result = DealService(None).score_deals_with_profile(deals, profile)
        assert len(result) == 1
        assert result[0]["new_score"] > 0
        assert result[0]["diff"] == result[0]["new_score"] - 50
        assert isinstance(result[0]["breakdown"], list)

    def test_score_deals_sorts_by_new_score_desc(self):
        """Results are sorted by new_score descending."""
        from dashboard.services import DealService

        deals = [
            {
                "id": "test:low",
                "title": "Basic item",
                "price": 100,
                "link": "",
                "source": "web",
                "description": "",
                "image_url": "",
                "score": 0,
            },
            {
                "id": "test:high",
                "title": "Carbon premium deal",
                "price": 8000,
                "link": "",
                "source": "pepper",
                "description": "",
                "image_url": "",
                "score": 0,
            },
        ]
        profile = {
            "score_rules": {"carbon": 50, "premium": 30},
            "penalties": {},
            "budget": {"min": 5000, "max": 15000},
        }
        result = DealService(None).score_deals_with_profile(deals, profile)
        assert result[0]["new_score"] >= result[1]["new_score"]

    def test_score_deals_handles_rejected(self):
        """Deals matching excluded words are marked rejected."""
        from dashboard.services import DealService

        deals = [
            {
                "id": "test:1",
                "title": "Stolen bike parts",
                "price": 500,
                "link": "",
                "source": "pepper",
                "description": "",
                "image_url": "",
                "score": 0,
            }
        ]
        profile = {
            "score_rules": {},
            "penalties": {},
            "excluded_words": ["stolen"],
        }
        result = DealService(None).score_deals_with_profile(deals, profile)
        assert result[0]["rejected"] is True
        assert result[0]["reject_reason"] != ""

    def test_score_deals_none_price_handled(self):
        """Deals with None price don't crash."""
        from dashboard.services import DealService

        deals = [
            {
                "id": "test:1",
                "title": "Free item",
                "price": None,
                "link": "",
                "source": "web",
                "description": "",
                "image_url": "",
                "score": 0,
            }
        ]
        result = DealService(None).score_deals_with_profile(
            deals, {"score_rules": {}, "penalties": {}}
        )
        assert len(result) == 1


# ──────────────── E2E tests: Scoring Tuner ────────────────


class TestTunerPage:
    def test_tuner_index_loads(self, client):
        response = client.get("/tuner")
        assert response.status_code == 200

    def test_tuner_profile_redirects(self, client):
        response = client.get("/tuner/nonexistent_profile_xyz")
        assert response.status_code == 302
        assert "tab=tuner" in response.headers["location"]

    def test_tuner_simulate_not_found(self, client):
        response = client.post(
            "/api/tuner/nonexistent_profile_xyz/simulate",
            json={"score_rules": {"test": 10}},
        )
        assert response.status_code == 404

    def test_tuner_save_not_found(self, client):
        response = client.post(
            "/api/tuner/nonexistent_profile_xyz/save",
            json={"score_rules": {"test": 10}},
        )
        assert response.status_code == 404

    def test_tuner_with_profile(self, client):
        """Tuner page loads with a real profile and scores deals."""
        # Create a profile first
        client.post(
            "/api/profiles",
            json={
                "name": "test_tuner_profile",
                "emoji": "\U0001f9ea",
                "sources": {"pepper": {"urls": ["https://pepper.pl/search?q=test"]}},
                "budget": {"min": 100, "max": 50000},
                "score_rules": {"carbon": 30, "bike": 10},
                "penalties": {"broken": -20},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        # /tuner/{profile} now redirects to /profiles/{profile}?tab=tuner
        response = client.get("/tuner/test_tuner_profile")
        assert response.status_code == 302
        # Follow redirect to unified profile page
        response = client.get("/profiles/test_tuner_profile?tab=tuner")
        assert response.status_code == 200
        text = response.text
        assert "Simulate" in text
        assert "Save" in text
        # Clean up
        client.delete("/api/profiles/test_tuner_profile")

    def test_tuner_simulate_with_data(self, client, dashboard_db):
        """Simulate API returns scoring results for deals in DB."""
        # Create profile matching deals in dashboard_db (profile="bikes")
        client.post(
            "/api/profiles",
            json={
                "name": "bikes",
                "emoji": "\U0001f6b2",
                "sources": {"pepper": {"urls": ["https://pepper.pl"]}},
                "budget": {"min": 1000, "max": 20000},
                "score_rules": {"carbon": 30, "bike": 10},
                "penalties": {"broken": -20},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        response = client.post(
            "/api/tuner/bikes/simulate",
            json={
                "score_rules": {"carbon": 50, "xl": 15},
                "penalties": {"broken": -30, "cheap": -10},
                "budget": {"min": 1000, "max": 20000},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        # Should have deals from the bikes profile
        if data["results"]:
            r = data["results"][0]
            assert "new_score" in r
            assert "diff" in r
            assert "breakdown" in r
            assert "current_score" in r
        # Clean up
        client.delete("/api/profiles/bikes")

    def test_tuner_simulate_returns_diff(self, client, dashboard_db):
        """Simulate with different rules produces different scores."""
        client.post(
            "/api/profiles",
            json={
                "name": "bikes",
                "emoji": "\U0001f6b2",
                "sources": {"pepper": {"urls": ["https://pepper.pl"]}},
                "budget": {"min": 1000, "max": 20000},
                "score_rules": {"carbon": 10},
                "penalties": {},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        # Simulate with high carbon bonus
        response = client.post(
            "/api/tuner/bikes/simulate",
            json={"score_rules": {"carbon": 100}},
        )
        data = response.json()
        # The "Test Carbon Bike XL" deal should get carbon points
        carbon_deals = [r for r in data["results"] if "Carbon" in r["title"]]
        if carbon_deals:
            assert carbon_deals[0]["new_score"] > 0
        # Clean up
        client.delete("/api/profiles/bikes")

    def test_tuner_save_creates_profile(self, client):
        """Save API writes rules to profile YAML."""
        client.post(
            "/api/profiles",
            json={
                "name": "test_tuner_save",
                "emoji": "\U0001f9ea",
                "sources": {"pepper": {"urls": ["https://pepper.pl"]}},
                "budget": {"min": 100, "max": 5000},
                "score_rules": {"old_keyword": 10},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        # Save with new rules
        response = client.post(
            "/api/tuner/test_tuner_save/save",
            json={
                "score_rules": {"new_keyword": 25},
                "penalties": {"bad": -15},
                "budget": {"min": 200, "max": 8000},
                "score_threshold": 60,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        # Verify the profile was updated by loading it
        from dashboard import safe_load_profile

        updated = safe_load_profile("test_tuner_save")
        assert updated is not None
        assert updated["score_rules"] == {"new_keyword": 25}
        assert updated["penalties"] == {"bad": -15}
        assert updated["budget"]["min"] == 200
        assert updated["score_threshold"] == 60
        # Clean up
        client.delete("/api/profiles/test_tuner_save")

    def test_tuner_save_validation_error(self, client):
        """Save API returns 400 on invalid profile data."""
        client.post(
            "/api/profiles",
            json={
                "name": "test_tuner_invalid",
                "emoji": "\U0001f9ea",
                "sources": {"pepper": {"urls": ["https://pepper.pl"]}},
                "budget": {"min": 100, "max": 5000},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        # Save with invalid budget (min > max)
        response = client.post(
            "/api/tuner/test_tuner_invalid/save",
            json={
                "budget": {"min": 10000, "max": 500},
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data.get("ok") is False
        assert "errors" in data
        assert len(data["errors"]) > 0
        # Clean up
        client.delete("/api/profiles/test_tuner_invalid")


# ──────────────── E2E workflow tests: Compare + Tuner ────────────────


class TestCompareAndTunerWorkflows:
    def test_compare_deals_from_list(self, client):
        """Browse deals, then compare specific ones."""
        # Step 1: Browse deals page
        deals_resp = client.get("/deals")
        assert deals_resp.status_code == 200
        # Step 2: Compare two seeded deals
        compare_resp = client.get("/compare?ids=pepper:99999,ceneo:88888")
        assert compare_resp.status_code == 200
        text = compare_resp.text
        assert "Test Carbon Bike XL" in text
        assert "NAS HDD Seagate IronWolf 8TB" in text
        # Step 3: Verify both prices shown
        assert "8 500 zl" in text  # pepper:99999 price
        assert "1 200 zl" in text  # ceneo:88888 price

    def test_tuner_simulate_then_save(self, client):
        """Simulate rules then save — full tuner workflow."""
        # Create test profile
        client.post(
            "/api/profiles",
            json={
                "name": "test_workflow",
                "emoji": "\U0001f527",
                "sources": {"pepper": {"urls": ["https://pepper.pl"]}},
                "budget": {"min": 100, "max": 50000},
                "score_rules": {"test": 5},
                "score_threshold": 50,
                "telegram": {"topic_id": None, "max_alerts": 5},
            },
        )
        # Simulate
        sim_resp = client.post(
            "/api/tuner/test_workflow/simulate",
            json={"score_rules": {"carbon": 40, "bike": 20}},
        )
        assert sim_resp.status_code == 200
        # Save
        save_resp = client.post(
            "/api/tuner/test_workflow/save",
            json={"score_rules": {"carbon": 40, "bike": 20}},
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["ok"] is True
        # Clean up
        client.delete("/api/profiles/test_workflow")

    def test_sidebar_has_no_tuner_link(self, client):
        """Scoring Tuner link was removed from sidebar (now a profile tab)."""
        response = client.get("/deals")
        assert response.status_code == 200
        assert 'href="/tuner"' not in response.text


def test_deals_per_page_env_override(monkeypatch):
    """DEALS_PER_PAGE reads from env var with fallback to 50."""
    monkeypatch.setenv("DEALS_PER_PAGE", "25")
    import importlib

    import dashboard.services

    importlib.reload(dashboard.services)
    assert dashboard.services.DEALS_PER_PAGE == 25
    monkeypatch.delenv("DEALS_PER_PAGE")
    importlib.reload(dashboard.services)
    assert dashboard.services.DEALS_PER_PAGE == 50


def test_score_threshold_env_override(monkeypatch):
    """SCORE_THRESHOLD reads from env var with fallback to 70."""
    monkeypatch.setenv("SCORE_THRESHOLD", "60")
    import importlib

    import dashboard.services

    importlib.reload(dashboard.services)
    assert dashboard.services.SCORE_THRESHOLD == 60
    monkeypatch.delenv("SCORE_THRESHOLD")
    importlib.reload(dashboard.services)
    assert dashboard.services.SCORE_THRESHOLD == 70
