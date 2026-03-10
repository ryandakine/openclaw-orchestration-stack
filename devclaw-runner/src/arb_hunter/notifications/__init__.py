"""Telegram Notification System for Arbitrage Hunter.

Provides formatted alerts, rate limiting, history tracking, and mute functionality
for arbitrage opportunity notifications.
"""

from .telegram_bot import TelegramBot, TelegramBotError
from .formatter import AlertFormatter, format_opportunity_alert
from .ratelimiter import AlertRateLimiter, RateLimitRule
from .history import AlertHistory, AlertRecord

__all__ = [
    "TelegramBot",
    "TelegramBotError",
    "AlertFormatter",
    "format_opportunity_alert",
    "AlertRateLimiter",
    "RateLimitRule",
    "AlertHistory",
    "AlertRecord",
]
