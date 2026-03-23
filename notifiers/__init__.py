"""Notifier registry — notification backends."""

from .notion import NotionNotifier
from .telegram import TelegramNotifier

__all__ = ["TelegramNotifier", "NotionNotifier"]
