"""
Telegram Configuration for Notifications.

Manages Telegram bot settings for arbitrage alerts and monitoring notifications.
Includes rate limiting and filtering capabilities.
"""

from dataclasses import dataclass, field
from typing import Self
import re


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    """
    Telegram bot configuration for notifications.
    
    Provides settings for bot authentication, rate limiting, and
    alert filtering to prevent notification spam.
    
    Attributes:
        enabled: Whether Telegram notifications are enabled
        bot_token: Telegram Bot API token from @BotFather
        chat_id: Target chat ID for notifications
        rate_limit_per_minute: Max messages per minute
        min_profit_alert_usd: Minimum profit to trigger alert
        alert_on_errors: Whether to alert on system errors
        alert_on_opportunities: Whether to alert on arb opportunities
        alert_on_executions: Whether to alert on trade executions
        include_details: Include full opportunity details in messages
        silent_hours_start: Hour to start silent mode (24h format, -1 to disable)
        silent_hours_end: Hour to end silent mode (24h format, -1 to disable)
    """
    
    enabled: bool = field(default=False)
    """Master switch for Telegram notifications."""
    
    bot_token: str | None = field(default=None)
    """Telegram Bot Token from @BotFather. Format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz"""
    
    chat_id: str | None = field(default=None)
    """Target chat ID. Can be user ID, group ID (negative), or channel username."""
    
    rate_limit_per_minute: int = field(default=20)
    """Maximum number of messages allowed per minute."""
    
    min_profit_alert_usd: float = field(default=10.0)
    """Only send alerts for opportunities with profit >= this amount."""
    
    alert_on_errors: bool = field(default=True)
    """Send alerts for system errors and exceptions."""
    
    alert_on_opportunities: bool = field(default=True)
    """Send alerts when arbitrage opportunities are found."""
    
    alert_on_executions: bool = field(default=True)
    """Send alerts when trades are executed."""
    
    alert_on_startup: bool = field(default=True)
    """Send alert when system starts up."""
    
    alert_on_shutdown: bool = field(default=True)
    """Send alert when system shuts down."""
    
    include_details: bool = field(default=True)
    """Include detailed information in opportunity alerts."""
    
    silent_hours_start: int = field(default=-1)
    """Start hour for silent mode (0-23, -1 to disable)."""
    
    silent_hours_end: int = field(default=-1)
    """End hour for silent mode (0-23, -1 to disable)."""
    
    retry_attempts: int = field(default=3)
    """Number of retry attempts for failed messages."""
    
    retry_delay_seconds: float = field(default=1.0)
    """Delay between retry attempts."""
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.enabled:
            self._validate_bot_token()
            self._validate_chat_id()
        
        self._validate_rate_limit()
        self._validate_silent_hours()
        self._validate_retry_settings()
    
    def _validate_bot_token(self) -> None:
        """Validate bot token format."""
        if not self.bot_token:
            raise ValueError("bot_token is required when Telegram is enabled")
        
        # Telegram bot token format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
        token_pattern = re.compile(r'^\d+:[A-Za-z0-9_-]{35,}$')
        if not token_pattern.match(self.bot_token):
            raise ValueError(
                "Invalid bot_token format. Expected: <numbers>:<alphanumeric>"
            )
    
    def _validate_chat_id(self) -> None:
        """Validate chat ID format."""
        if not self.chat_id:
            raise ValueError("chat_id is required when Telegram is enabled")
        
        # Chat ID can be:
        # - Numeric (user ID or group ID)
        # - String starting with @ (channel username)
        # - String for topic/thread IDs
        if isinstance(self.chat_id, str):
            if self.chat_id.startswith('@'):
                # Channel username format: @channelname
                if len(self.chat_id) < 2:
                    raise ValueError("Channel username cannot be empty")
            elif self.chat_id.lstrip('-').isdigit():
                # Numeric string
                pass
            else:
                raise ValueError(
                    "chat_id must be numeric, negative numeric (group), "
                    "or @channelname format"
                )
    
    def _validate_rate_limit(self) -> None:
        """Validate rate limiting settings."""
        if self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be at least 1")
        if self.rate_limit_per_minute > 100:
            raise ValueError("rate_limit_per_minute cannot exceed 100")
    
    def _validate_silent_hours(self) -> None:
        """Validate silent hours configuration."""
        if self.silent_hours_start != -1:
            if not (0 <= self.silent_hours_start <= 23):
                raise ValueError("silent_hours_start must be 0-23 or -1")
        if self.silent_hours_end != -1:
            if not (0 <= self.silent_hours_end <= 23):
                raise ValueError("silent_hours_end must be 0-23 or -1")
        
        # Both must be set or both disabled
        if (self.silent_hours_start == -1) != (self.silent_hours_end == -1):
            raise ValueError("Both silent_hours_start and silent_hours_end must be set or both -1")
    
    def _validate_retry_settings(self) -> None:
        """Validate retry configuration."""
        if self.retry_attempts < 0:
            raise ValueError("retry_attempts must be non-negative")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
    
    def should_alert_for_profit(self, profit_usd: float) -> bool:
        """
        Check if an alert should be sent based on profit threshold.
        
        Args:
            profit_usd: Estimated profit in USD
            
        Returns:
            True if alert should be sent
        """
        if not self.enabled:
            return False
        return profit_usd >= self.min_profit_alert_usd
    
    def is_silent_hours(self, current_hour: int) -> bool:
        """
        Check if current time falls within silent hours.
        
        Args:
            current_hour: Current hour in 24h format (0-23)
            
        Returns:
            True if currently in silent hours
        """
        if self.silent_hours_start == -1 or self.silent_hours_end == -1:
            return False
        
        if self.silent_hours_start <= self.silent_hours_end:
            # Same day range (e.g., 22:00 to 06:00 doesn't apply)
            return self.silent_hours_start <= current_hour <= self.silent_hours_end
        else:
            # Overnight range (e.g., 22:00 to 06:00)
            return current_hour >= self.silent_hours_start or current_hour <= self.silent_hours_end
    
    def format_opportunity_message(
        self,
        profit_usd: float,
        profit_pct: float,
        venue_a: str,
        venue_b: str,
        event_name: str,
        details: dict | None = None,
    ) -> str:
        """
        Format an opportunity alert message.
        
        Args:
            profit_usd: Estimated profit in USD
            profit_pct: Profit percentage
            venue_a: First venue name
            venue_b: Second venue name
            event_name: Event/market name
            details: Additional details dictionary
            
        Returns:
            Formatted message string
        """
        emoji = "🎯" if profit_usd >= 50 else "💰" if profit_usd >= 20 else "✨"
        
        message = f"""
{emoji} <b>Arbitrage Opportunity Detected!</b>

📊 <b>Event:</b> {event_name}
💵 <b>Est. Profit:</b> ${profit_usd:.2f} ({profit_pct:.2f}%)
🏛 <b>Venues:</b> {venue_a.title()} ↔️ {venue_b.title()}
"""
        
        if self.include_details and details:
            message += "\n📋 <b>Details:</b>\n"
            for key, value in details.items():
                message += f"  • {key}: {value}\n"
        
        return message.strip()
    
    def format_execution_message(
        self,
        success: bool,
        profit_usd: float,
        venue_a: str,
        venue_b: str,
        event_name: str,
        error: str | None = None,
    ) -> str:
        """
        Format a trade execution message.
        
        Args:
            success: Whether execution was successful
            profit_usd: Actual or estimated profit
            venue_a: First venue name
            venue_b: Second venue name
            event_name: Event name
            error: Error message if failed
            
        Returns:
            Formatted message string
        """
        if success:
            emoji = "✅"
            status = "EXECUTED"
        else:
            emoji = "❌"
            status = "FAILED"
        
        message = f"""
{emoji} <b>Trade {status}</b>

📊 <b>Event:</b> {event_name}
💵 <b>Profit:</b> ${profit_usd:.2f}
🏛 <b>Venues:</b> {venue_a.title()} ↔️ {venue_b.title()}
"""
        
        if error:
            message += f"\n⚠️ <b>Error:</b> {error}"
        
        return message.strip()
    
    def format_error_message(self, error_type: str, error_message: str, context: str = "") -> str:
        """
        Format an error alert message.
        
        Args:
            error_type: Type/category of error
            error_message: Error description
            context: Additional context
            
        Returns:
            Formatted message string
        """
        message = f"""
🚨 <b>System Error Alert</b>

⚠️ <b>Type:</b> {error_type}
📝 <b>Message:</b> {error_message}
"""
        if context:
            message += f"\n🔍 <b>Context:</b> {context}"
        
        return message.strip()
    
    def format_startup_message(self, version: str, environment: str) -> str:
        """Format system startup notification."""
        emoji = "🚀" if environment == "production" else "🔧"
        return f"""
{emoji} <b>OpenClaw Arbitrage Hunter Started</b>

📦 <b>Version:</b> {version}
🌍 <b>Environment:</b> {environment}
⏰ <b>Time:</b> System operational
""".strip()
    
    def format_shutdown_message(self, uptime_seconds: float) -> str:
        """Format system shutdown notification."""
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        return f"""
🛑 <b>OpenClaw Arbitrage Hunter Stopped</b>

⏱ <b>Uptime:</b> {hours}h {minutes}m
👋 <b>Status:</b> System shutdown complete
""".strip()
    
    def to_dict(self) -> dict:
        """Convert config to dictionary (excludes sensitive data)."""
        return {
            "enabled": self.enabled,
            "chat_id": self.chat_id,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "min_profit_alert_usd": self.min_profit_alert_usd,
            "alert_on_errors": self.alert_on_errors,
            "alert_on_opportunities": self.alert_on_opportunities,
            "alert_on_executions": self.alert_on_executions,
            "alert_on_startup": self.alert_on_startup,
            "alert_on_shutdown": self.alert_on_shutdown,
            "include_details": self.include_details,
            "silent_hours_start": self.silent_hours_start,
            "silent_hours_end": self.silent_hours_end,
            "retry_attempts": self.retry_attempts,
            "retry_delay_seconds": self.retry_delay_seconds,
        }
    
    @classmethod
    def from_env(cls) -> Self:
        """
        Create config from environment variables.
        
        Environment variables:
        - TELEGRAM_ENABLED
        - TELEGRAM_BOT_TOKEN
        - TELEGRAM_CHAT_ID
        - TELEGRAM_RATE_LIMIT_PER_MINUTE
        - TELEGRAM_MIN_PROFIT_ALERT_USD
        - etc.
        
        Returns:
            TelegramConfig instance
        """
        import os
        
        enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        
        return cls(
            enabled=enabled,
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            rate_limit_per_minute=int(os.getenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "20")),
            min_profit_alert_usd=float(os.getenv("TELEGRAM_MIN_PROFIT_ALERT_USD", "10.0")),
            alert_on_errors=os.getenv("TELEGRAM_ALERT_ON_ERRORS", "true").lower() == "true",
            alert_on_opportunities=os.getenv("TELEGRAM_ALERT_ON_OPPORTUNITIES", "true").lower() == "true",
            alert_on_executions=os.getenv("TELEGRAM_ALERT_ON_EXECUTIONS", "true").lower() == "true",
            alert_on_startup=os.getenv("TELEGRAM_ALERT_ON_STARTUP", "true").lower() == "true",
            alert_on_shutdown=os.getenv("TELEGRAM_ALERT_ON_SHUTDOWN", "true").lower() == "true",
            include_details=os.getenv("TELEGRAM_INCLUDE_DETAILS", "true").lower() == "true",
            silent_hours_start=int(os.getenv("TELEGRAM_SILENT_HOURS_START", "-1")),
            silent_hours_end=int(os.getenv("TELEGRAM_SILENT_HOURS_END", "-1")),
            retry_attempts=int(os.getenv("TELEGRAM_RETRY_ATTEMPTS", "3")),
            retry_delay_seconds=float(os.getenv("TELEGRAM_RETRY_DELAY_SECONDS", "1.0")),
        )


def get_default_telegram_config() -> TelegramConfig:
    """
    Get default Telegram configuration (disabled).
    
    Returns:
        TelegramConfig with defaults (notifications disabled)
    """
    return TelegramConfig()
