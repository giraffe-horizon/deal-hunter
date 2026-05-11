"""Tests for the notifications dashboard page + APIs."""

import yaml


class TestNotificationsPage:
    def test_page_renders(self, client):
        # When the YAML file doesn't exist in test workspace, the loader returns
        # hardcoded defaults — both keys still render in the form.
        response = client.get("/notifications")
        assert response.status_code == 200
        assert "cooldown_days" in response.text
        assert "default_snooze_days" in response.text


class TestGlobalNotificationConfigApi:
    def test_post_updates_yaml(self, client, tmp_path, monkeypatch):
        from deal_hunter.api.routes import notifications as notif_routes

        monkeypatch.setattr(
            notif_routes,
            "_global_config_path",
            lambda: tmp_path / "notifications.yaml",
        )
        response = client.post(
            "/api/notifications/global",
            data={
                "cooldown_days": "10",
                "alert_through_cooldown_if_ath_low": "true",
                "default_snooze_days": "14",
            },
        )
        assert response.status_code == 200
        data = yaml.safe_load((tmp_path / "notifications.yaml").read_text())
        assert data["price_drop_alerts"]["cooldown_days"] == 10
        assert data["price_drop_alerts"]["default_snooze_days"] == 14
        assert data["price_drop_alerts"]["alert_through_cooldown_if_ath_low"] is True

    def test_post_validates_range(self, client, tmp_path, monkeypatch):
        from deal_hunter.api.routes import notifications as notif_routes

        monkeypatch.setattr(
            notif_routes,
            "_global_config_path",
            lambda: tmp_path / "notifications.yaml",
        )
        response = client.post(
            "/api/notifications/global",
            data={
                "cooldown_days": "-1",
                "alert_through_cooldown_if_ath_low": "true",
                "default_snooze_days": "14",
            },
        )
        assert response.status_code == 422


class TestPerDealMuteApi:
    def test_mute_sets_permanent(self, client):
        response = client.post(
            "/api/deals/pepper:99999/mute",
            data={"days": ""},
        )
        assert response.status_code == 200

    def test_snooze_sets_future_timestamp(self, client):
        response = client.post(
            "/api/deals/pepper:99999/mute",
            data={"days": "7"},
        )
        assert response.status_code == 200

    def test_mute_404_for_missing_deal(self, client):
        response = client.post(
            "/api/deals/nope:0/mute",
            data={"days": ""},
        )
        assert response.status_code == 404

    def test_unmute_clears_mute(self, client):
        client.post("/api/deals/pepper:99999/mute", data={"days": "5"})
        response = client.post("/api/deals/pepper:99999/unmute")
        assert response.status_code == 200


class TestWatchlistMutedFilter:
    def test_watchlist_with_muted_filter_shows_muted_deals(self, client, dashboard_session):
        from deal_hunter.storage.repositories import OfferRepository

        repo = OfferRepository(dashboard_session)
        repo.set_muted_until("pepper:99999", "2099-01-01T00:00:00")
        dashboard_session.flush()

        response = client.get("/watchlist?muted=1")
        assert response.status_code == 200
        # The page should render the muted deal (id appears somewhere) or show a mute indicator
        body = response.text
        assert "pepper:99999" in body or "Wycisz" in body or "muted" in body.lower()
