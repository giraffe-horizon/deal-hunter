"""Notion notifier — saves deals to Notion database."""

import logging
import os
import re
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

NOTION_VERSION = "2025-09-03"
NOTION_API_URL = "https://api.notion.com/v1/pages"


class NotionNotifier:
    """Saves deals to a Notion database."""

    def __init__(self, api_key_path: str) -> None:
        self.api_key = self._load_key(api_key_path)

    @staticmethod
    def _load_key(path: str) -> str | None:
        """Load Notion API key from file."""
        expanded = os.path.expanduser(path)
        try:
            with open(expanded) as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Notion: cannot read key from {expanded}: {e}")
            return None

    def save_deal(
        self,
        deal,
        score: int,
        plus: list[str],
        database_id: str,
        profile_name: str = "",
        profile: dict | None = None,
    ) -> None:
        """Save a deal to Notion. Errors are logged but don't crash."""
        if not self.api_key:
            logger.warning("Notion: no API key, skipping")
            return

        if not database_id:
            return

        category = self._detect_category(deal, profile=profile, profile_name=profile_name)
        today = datetime.now().strftime("%Y-%m-%d")
        notes = ", ".join(plus[:3]) if plus else ""

        source_names = {
            "pepper": "Pepper.pl",
            "ceneo": "Ceneo.pl",
            "proshop": "Proshop.pl",
        }
        source_display = source_names.get(deal.source, deal.source)

        # Property names match the Notion database schema (Polish column names)
        properties: dict = {
            "Nazwa": {"title": [{"text": {"content": deal.title[:2000]}}]},
            "Status": {"select": {"name": "\U0001f525 Aktywna"}},
            "\u0179r\u00f3d\u0142o": {"select": {"name": source_display}},
            "Kategoria": {"select": {"name": category}},
            "Data znalezienia": {"date": {"start": today}},
            "Notatki": {"rich_text": [{"text": {"content": notes[:2000]}}]},
            "Score": {"number": score},
        }

        if deal.price > 0:
            properties["Cena"] = {"number": deal.price}

        if deal.link:
            properties["Link"] = {"url": deal.link}

        # Detect discount
        text = (deal.title + " " + deal.description).lower()
        discount_match = re.search(r"(-?\d+)\s*%", text)
        if discount_match:
            properties["Rabat"] = {
                "rich_text": [{"text": {"content": f"{discount_match.group(1)}%"}}]
            }

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

        try:
            resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code in (200, 201):
                logger.info(f"Notion: saved '{deal.title[:60]}' (score: {score})")
            else:
                logger.error(
                    f"Notion: HTTP {resp.status_code} for '{deal.title[:60]}': {resp.text[:200]}"
                )
        except Exception as e:
            logger.error(f"Notion: exception saving '{deal.title[:60]}': {e}")

    @staticmethod
    def _detect_category(deal, profile: dict | None = None, profile_name: str = "") -> str:
        """Detect product category from title and description using profile categories."""
        categories: dict = {}
        if profile:
            notion_cfg = profile.get("notion")
            categories = notion_cfg.get("categories", {}) if isinstance(notion_cfg, dict) else {}

        if not categories:
            return profile_name if profile_name else "other"

        text = (deal.title + " " + deal.description).lower()
        for category, keywords in categories.items():
            if any(kw.lower() in text for kw in keywords):
                return str(category)
        return profile_name if profile_name else "other"
