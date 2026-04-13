"""Tests for visualization/charts.py — chart generation and send_photo."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ──


@pytest.fixture
def mock_db():
    """Create a mock SQLiteStorage with sample data."""
    db = MagicMock()

    db.get_deal.return_value = {
        "id": "pepper:12345",
        "title": "Canyon Endurace CF 8 Di2",
        "price": 10499,
        "link": "https://example.com/deal",
        "source": "pepper",
        "profile": "bikes",
    }

    now = datetime.now()
    db.get_price_history.return_value = [
        {
            "deal_id": "pepper:12345",
            "price": 12999,
            "recorded_at": (now - timedelta(days=10)).isoformat(),
        },
        {
            "deal_id": "pepper:12345",
            "price": 11999,
            "recorded_at": (now - timedelta(days=7)).isoformat(),
        },
        {
            "deal_id": "pepper:12345",
            "price": 10999,
            "recorded_at": (now - timedelta(days=3)).isoformat(),
        },
        {"deal_id": "pepper:12345", "price": 10499, "recorded_at": now.isoformat()},
    ]

    db.get_deals.return_value = [
        {
            "id": "pepper:12345",
            "title": "Canyon Endurace CF 8 Di2",
            "price": 10499,
            "source": "pepper",
            "profile": "bikes",
        },
        {
            "id": "pepper:67890",
            "title": "Giant Defy Advanced 2",
            "price": 8999,
            "source": "pepper",
            "profile": "bikes",
        },
    ]

    return db


@pytest.fixture
def sample_drops():
    """Sample price drops for digest chart."""
    return [
        {
            "title": "Canyon Endurace CF 8 Di2",
            "old_price": 12999,
            "new_price": 10499,
            "diff_percent": 19.2,
            "diff_pln": 2500,
            "is_lowest_ever": True,
        },
        {
            "title": "Giant Defy Advanced 2",
            "old_price": 8999,
            "new_price": 7999,
            "diff_percent": 11.1,
            "diff_pln": 1000,
            "is_lowest_ever": False,
        },
        {
            "title": "Shimano 105 Di2 Group",
            "old_price": 5999,
            "new_price": 5499,
            "diff_percent": 8.3,
            "diff_pln": 500,
            "is_lowest_ever": False,
        },
    ]


def _is_png(path: Path) -> bool:
    """Check if a file starts with a PNG signature."""
    with path.open("rb") as f:
        header = f.read(8)
    return header == b"\x89PNG\r\n\x1a\n"


# ── generate_price_chart ──


class TestGeneratePriceChart:
    def test_generates_valid_png(self, mock_db, tmp_path):
        from visualization.charts import generate_price_chart

        output = tmp_path / "test_chart.png"
        result = generate_price_chart("pepper:12345", mock_db, output_path=str(output))

        assert result == output
        assert output.exists()
        assert _is_png(output)

    def test_default_output_path(self, mock_db):
        from visualization.charts import generate_price_chart

        result = generate_price_chart("pepper:12345", mock_db)

        assert result.exists()
        assert _is_png(result)
        # Cleanup
        result.unlink(missing_ok=True)

    def test_deal_not_found(self, mock_db):
        from visualization.charts import generate_price_chart

        mock_db.get_deal.return_value = None

        with pytest.raises(ValueError, match="Nie znaleziono oferty"):
            generate_price_chart("nonexistent:999", mock_db)

    def test_no_price_history(self, mock_db):
        from visualization.charts import generate_price_chart

        mock_db.get_price_history.return_value = []

        with pytest.raises(ValueError, match="Brak historii cen"):
            generate_price_chart("pepper:12345", mock_db)


# ── generate_digest_chart ──


class TestGenerateDigestChart:
    def test_generates_valid_png(self, sample_drops, tmp_path):
        from visualization.charts import generate_digest_chart

        output = tmp_path / "digest.png"
        result = generate_digest_chart(sample_drops, output_path=str(output))

        assert result == output
        assert output.exists()
        assert _is_png(output)

    def test_empty_drops_raises(self):
        from visualization.charts import generate_digest_chart

        with pytest.raises(ValueError, match="Brak danych"):
            generate_digest_chart([])

    def test_default_output_path(self, sample_drops):
        from visualization.charts import generate_digest_chart

        result = generate_digest_chart(sample_drops)

        assert result.exists()
        assert _is_png(result)
        result.unlink(missing_ok=True)


# ── generate_trend_chart ──


class TestGenerateTrendChart:
    def test_generates_valid_png(self, mock_db, tmp_path):
        from visualization.charts import generate_trend_chart

        output = tmp_path / "trend.png"
        result = generate_trend_chart("bikes", mock_db, days=30, output_path=str(output))

        assert result == output
        assert output.exists()
        assert _is_png(output)

    def test_no_deals_raises(self, mock_db):
        from visualization.charts import generate_trend_chart

        mock_db.get_deals.return_value = []

        with pytest.raises(ValueError, match="Brak ofert"):
            generate_trend_chart("empty_profile", mock_db)

    def test_no_price_data_raises(self, mock_db):
        from visualization.charts import generate_trend_chart

        mock_db.get_price_history.return_value = []

        with pytest.raises(ValueError, match="Brak danych cenowych"):
            generate_trend_chart("bikes", mock_db)


# ── Lazy import ──


class TestLazyImport:
    def test_import_error_message(self):
        # Temporarily hide matplotlib
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "matplotlib" or name.startswith("matplotlib."):
                raise ImportError("No module named 'matplotlib'")
            return real_import(name, *args, **kwargs)

        # Need to reload charts module with mocked import
        with patch("builtins.__import__", side_effect=mock_import):
            from visualization.charts import _import_matplotlib

            with pytest.raises(ImportError, match="matplotlib is required"):
                _import_matplotlib()


# ── send_photo ──


class TestSendPhoto:
    def test_send_photo_success(self, tmp_path):
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("test_token", "test_chat")

        # Create a dummy file
        photo = tmp_path / "test.png"
        photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("notifiers.telegram.requests.post", return_value=mock_response) as mock_post,
            patch("notifiers.telegram.time.sleep"),
        ):
            notifier.send_photo(str(photo), caption="Test caption", topic_id=42)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["data"]["chat_id"] == "test_chat"
        assert call_kwargs[1]["data"]["caption"] == "Test caption"
        assert call_kwargs[1]["data"]["message_thread_id"] == "42"
        assert "photo" in call_kwargs[1]["files"]

    def test_send_photo_retry_on_429(self, tmp_path):
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("test_token", "test_chat")

        photo = tmp_path / "test.png"
        photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {"parameters": {"retry_after": 1}}

        resp_200 = MagicMock()
        resp_200.status_code = 200

        with (
            patch(
                "notifiers.telegram.requests.post", side_effect=[resp_429, resp_200]
            ) as mock_post,
            patch("notifiers.telegram.time.sleep"),
        ):
            notifier.send_photo(str(photo))

        assert mock_post.call_count == 2

    def test_send_photo_no_caption(self, tmp_path):
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("test_token", "test_chat")

        photo = tmp_path / "test.png"
        photo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("notifiers.telegram.requests.post", return_value=mock_response) as mock_post,
            patch("notifiers.telegram.time.sleep"),
        ):
            notifier.send_photo(str(photo))

        call_kwargs = mock_post.call_args
        assert "caption" not in call_kwargs[1]["data"]
