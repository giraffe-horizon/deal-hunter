"""Notifier registry — notification backends."""

from .telegram import TelegramNotifier

__all__ = ["TelegramNotifier"]
