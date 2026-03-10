"""Alert generation and sending for Telegram.

Module 4: Telegram Alert Formatter

This module handles:
- Formatting arbitrage opportunities into readable alerts
- Deduplication to prevent spam
- Prioritization (top N alerts only)
- Stale opportunity tracking
- Telegram API integration
"""

from .alert_template import (
    AlertTemplateData,
    AlertTemplateEngine,
    ALERT_TEMPLATE,
    COMPACT_TEMPLATE,
    EXPIRED_TEMPLATE,
)
from .alert_builder import AlertBuilder, AlertFormatter
from .alert_deduplicator import AlertDeduplicator, SentAlertRecord
from .alert_prioritizer import AlertPrioritizer, PrioritizedAlert
from .stale_alert_handler import StaleAlertHandler, TrackedOpportunity
from .telegram_sender import (
    TelegramSender,
    TelegramConfig,
    TelegramRateLimiter,
    TelegramAPIError,
    create_sender_from_env,
)

__all__ = [
    # Templates
    "AlertTemplateData",
    "AlertTemplateEngine",
    "ALERT_TEMPLATE",
    "COMPACT_TEMPLATE",
    "EXPIRED_TEMPLATE",
    # Builder
    "AlertBuilder",
    "AlertFormatter",
    # Deduplicator
    "AlertDeduplicator",
    "SentAlertRecord",
    # Prioritizer
    "AlertPrioritizer",
    "PrioritizedAlert",
    # Stale Handler
    "StaleAlertHandler",
    "TrackedOpportunity",
    # Sender
    "TelegramSender",
    "TelegramConfig",
    "TelegramRateLimiter",
    "TelegramAPIError",
    "create_sender_from_env",
]
