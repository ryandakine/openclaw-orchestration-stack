"""Telegram Bot interface for sending arbitrage alerts.

Integrates formatter, rate limiter, and history tracking into a
unified interface for sending notifications.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .formatter import AlertFormatter, FormattedAlert, format_opportunity_alert
from .ratelimiter import AlertRateLimiter, MuteManager
from .history import AlertHistory


@dataclass
class TelegramBotConfig:
    """Configuration for TelegramBot."""
    
    bot_token: str | None = None
    chat_id: str | None = None
    enabled: bool = True
    test_mode: bool = False  # If True, prints to console instead of sending
    include_details: bool = True
    min_profit_alert_pct: float = 0.01  # 1% minimum
    rate_limit_rules: list | None = None
    history_dir: str | None = None
    
    @classmethod
    def from_env(cls) -> TelegramBotConfig:
        """Create config from environment variables.
        
        Environment variables:
            TELEGRAM_BOT_TOKEN: Bot token from @BotFather
            TELEGRAM_CHAT_ID: Target chat ID
            TELEGRAM_ENABLED: "true" to enable (default: true)
            TELEGRAM_TEST_MODE: "true" for test mode
            TELEGRAM_MIN_PROFIT_PCT: Minimum profit % to alert
        """
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
            enabled=os.environ.get("TELEGRAM_ENABLED", "true").lower() == "true",
            test_mode=os.environ.get("TELEGRAM_TEST_MODE", "false").lower() == "true",
            include_details=os.environ.get("TELEGRAM_INCLUDE_DETAILS", "true").lower() == "true",
            min_profit_alert_pct=float(os.environ.get("TELEGRAM_MIN_PROFIT_PCT", "0.01")),
            history_dir=os.environ.get("TELEGRAM_HISTORY_DIR"),
        )


class TelegramBotError(Exception):
    """Error from Telegram Bot operations."""
    pass


class TelegramBot:
    """Unified Telegram bot for arbitrage alerts.
    
    Combines formatting, rate limiting, and history tracking into
    a simple interface for sending alerts.
    """
    
    TELEGRAM_API_BASE = "https://api.telegram.org"
    
    def __init__(
        self,
        config: TelegramBotConfig | None = None,
        formatter: AlertFormatter | None = None,
        rate_limiter: AlertRateLimiter | None = None,
        mute_manager: MuteManager | None = None,
        history: AlertHistory | None = None,
    ):
        """Initialize the Telegram bot.
        
        Args:
            config: Bot configuration
            formatter: Message formatter
            rate_limiter: Rate limiter for alerts
            mute_manager: Mute manager
            history: Alert history tracker
        """
        self.config = config or TelegramBotConfig()
        self.formatter = formatter or AlertFormatter(
            include_details=self.config.include_details
        )
        self.rate_limiter = rate_limiter or AlertRateLimiter()
        self.mute_manager = mute_manager or MuteManager()
        self.history = history or AlertHistory(
            history_dir=self.config.history_dir
        )
        
        self._client: httpx.AsyncClient | None = None
        self._initialized = False
    
    async def _ensure_initialized(self) -> None:
        """Ensure async initialization is complete."""
        if not self._initialized:
            await self.history.load()
            self._initialized = True
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def send_opportunity_alert(
        self,
        event_title: str,
        side_a_venue: str,
        side_a_outcome: str,
        side_a_odds: float,
        side_b_venue: str,
        side_b_outcome: str,
        side_b_odds: float,
        profit_pct: float,
        total_stake: float,
        side_a_stake: float,
        side_b_stake: float,
        alert_id: str | None = None,
        sport: str | None = None,
        start_time: datetime | None = None,
        expires_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Send an arbitrage opportunity alert.
        
        Args:
            event_title: Event name
            side_a_venue: First venue
            side_a_outcome: First outcome
            side_a_odds: First odds (decimal)
            side_b_venue: Second venue
            side_b_outcome: Second outcome
            side_b_odds: Second odds (decimal)
            profit_pct: Profit percentage after fees
            total_stake: Total recommended stake
            side_a_stake: Stake for side A
            side_b_stake: Stake for side B
            alert_id: Unique alert ID (generated if not provided)
            sport: Sport category
            start_time: Event start time
            expires_minutes: Minutes until expiry
            
        Returns:
            Result dictionary with status and details
        """
        await self._ensure_initialized()
        
        # Generate alert ID if not provided
        if alert_id is None:
            alert_id = f"{event_title.lower().replace(' ', '_')}_{int(datetime.utcnow().timestamp())}"
        
        # Check minimum profit threshold
        if profit_pct < self.config.min_profit_alert_pct:
            return {
                "sent": False,
                "reason": f"Profit {profit_pct:.2%} below threshold {self.config.min_profit_alert_pct:.2%}",
                "alert_id": alert_id,
            }
        
        # Check if muted
        is_muted, mute_reason = await self.mute_manager.is_muted(
            event_title, side_a_venue, side_b_venue, sport
        )
        if is_muted:
            return {
                "sent": False,
                "reason": f"Muted: {mute_reason}",
                "alert_id": alert_id,
            }
        
        # Check rate limits
        allowed, rate_details = await self.rate_limiter.check_rate_limit(
            event_title, side_a_venue, side_b_venue, sport
        )
        if not allowed:
            return {
                "sent": False,
                "reason": f"Rate limited: {rate_details.get('blocked_by')}",
                "alert_id": alert_id,
                "rate_limit_details": rate_details,
            }
        
        # Format the message
        message = format_opportunity_alert(
            event_title=event_title,
            side_a_venue=side_a_venue,
            side_a_outcome=side_a_outcome,
            side_a_odds=side_a_odds,
            side_b_venue=side_b_venue,
            side_b_outcome=side_b_outcome,
            side_b_odds=side_b_odds,
            profit_pct=profit_pct,
            total_stake=total_stake,
            side_a_stake=side_a_stake,
            side_b_stake=side_b_stake,
            start_time=start_time,
            expires_minutes=expires_minutes,
        )
        
        # Send the alert
        result = await self._send_message(message, alert_id)
        
        # Record in history
        await self.history.record(
            alert_id=alert_id,
            event_title=event_title,
            message=message,
            profit_pct=profit_pct,
            sport=sport,
            venues=[side_a_venue, side_b_venue],
            success=result.get("sent", False),
            error_message=result.get("error"),
        )
        
        # Update rate limiter if sent
        if result.get("sent"):
            await self.rate_limiter.record_alert(
                event_title, side_a_venue, side_b_venue, sport
            )
        
        return result
    
    async def send_system_alert(
        self,
        alert_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a system alert (errors, startup, etc.).
        
        Args:
            alert_type: Type of alert (error, startup, shutdown, info)
            message: Main message
            details: Additional details
            
        Returns:
            Result dictionary
        """
        await self._ensure_initialized()
        
        formatted = self.formatter.format_system_alert(
            alert_type=alert_type,
            message=message,
            details=details,
        )
        
        alert_id = f"system_{alert_type}_{int(datetime.utcnow().timestamp())}"
        
        result = await self._send_message(formatted.message, alert_id)
        
        await self.history.record(
            alert_id=alert_id,
            event_title=f"System: {alert_type}",
            message=formatted.message,
            profit_pct=0.0,
            success=result.get("sent", False),
            error_message=result.get("error"),
            metadata={"type": alert_type, "details": details},
        )
        
        return result
    
    async def send_from_opportunity(self, opportunity: Any) -> dict[str, Any]:
        """Send alert from an ArbOpportunity object.
        
        Args:
            opportunity: ArbOpportunity dataclass instance
            
        Returns:
            Result dictionary
        """
        await self._ensure_initialized()
        
        formatted = self.formatter.format_from_opportunity(opportunity)
        
        # Extract required fields from opportunity
        left_leg = getattr(opportunity, 'left_leg', {})
        right_leg = getattr(opportunity, 'right_leg', {})
        
        return await self.send_opportunity_alert(
            event_title=getattr(opportunity, 'event_title', 'Unknown'),
            side_a_venue=left_leg.get('venue', 'Venue A'),
            side_a_outcome=left_leg.get('side', 'Side A'),
            side_a_odds=left_leg.get('odds', 2.0),
            side_b_venue=right_leg.get('venue', 'Venue B'),
            side_b_outcome=right_leg.get('side', 'Side B'),
            side_b_odds=right_leg.get('odds', 2.0),
            profit_pct=getattr(opportunity, 'net_edge_pct', 0.0),
            total_stake=getattr(opportunity, 'max_size', 0.0),
            side_a_stake=0.0,  # Will be calculated
            side_b_stake=0.0,  # Will be calculated
            alert_id=getattr(opportunity, 'arb_id', None),
            sport=left_leg.get('sport'),
            expires_at=getattr(opportunity, 'expires_at', None),
        )
    
    async def _send_message(self, message: str, alert_id: str) -> dict[str, Any]:
        """Send message to Telegram or print in test mode.
        
        Args:
            message: Message to send
            alert_id: Alert identifier
            
        Returns:
            Result dictionary
        """
        # Test mode: print to console
        if self.config.test_mode:
            print("\n" + "=" * 50)
            print("TELEGRAM ALERT (TEST MODE)")
            print("=" * 50)
            print(message)
            print("=" * 50 + "\n")
            return {
                "sent": True,
                "test_mode": True,
                "alert_id": alert_id,
            }
        
        # Check if enabled
        if not self.config.enabled:
            return {
                "sent": False,
                "reason": "Bot is disabled",
                "alert_id": alert_id,
            }
        
        # Validate config
        if not self.config.bot_token or not self.config.chat_id:
            return {
                "sent": False,
                "reason": "Missing bot_token or chat_id",
                "alert_id": alert_id,
            }
        
        # Send via Telegram API
        try:
            url = f"{self.TELEGRAM_API_BASE}/bot{self.config.bot_token}/sendMessage"
            
            payload = {
                "chat_id": self.config.chat_id,
                "text": message,
                "parse_mode": "MarkdownV2",
                "disable_notification": False,
            }
            
            client = await self._get_client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get("ok"):
                return {
                    "sent": True,
                    "message_id": data["result"]["message_id"],
                    "alert_id": alert_id,
                }
            else:
                return {
                    "sent": False,
                    "error": data.get("description", "Unknown error"),
                    "alert_id": alert_id,
                }
                
        except httpx.HTTPStatusError as e:
            return {
                "sent": False,
                "error": f"HTTP error: {e.response.status_code}",
                "alert_id": alert_id,
            }
        except httpx.RequestError as e:
            return {
                "sent": False,
                "error": f"Request error: {e}",
                "alert_id": alert_id,
            }
    
    async def test_connection(self) -> dict[str, Any]:
        """Test Telegram connection.
        
        Returns:
            Status dictionary
        """
        if self.config.test_mode:
            return {
                "connected": True,
                "test_mode": True,
                "bot_info": {"username": "test_mode_bot"},
            }
        
        if not self.config.bot_token:
            return {
                "connected": False,
                "error": "No bot token configured",
            }
        
        try:
            url = f"{self.TELEGRAM_API_BASE}/bot{self.config.bot_token}/getMe"
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data.get("ok"):
                return {
                    "connected": True,
                    "bot_info": data["result"],
                }
            else:
                return {
                    "connected": False,
                    "error": data.get("description", "Unknown error"),
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
    
    async def get_stats(self, days: int = 7) -> dict[str, Any]:
        """Get alert statistics.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Statistics dictionary
        """
        await self._ensure_initialized()
        
        history_stats = await self.history.get_stats(days=days)
        rate_limit_status = self.rate_limiter.get_status()
        muted_items = await self.mute_manager.get_muted_items()
        
        return {
            "history": history_stats,
            "rate_limiter": rate_limit_status,
            "muted": muted_items,
            "config": {
                "enabled": self.config.enabled,
                "test_mode": self.config.test_mode,
                "min_profit_alert_pct": self.config.min_profit_alert_pct,
            },
        }
    
    async def mute_event(
        self,
        event_title: str,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Mute alerts for an event.
        
        Args:
            event_title: Event to mute
            duration_minutes: Duration (None = permanent)
            
        Returns:
            Result dictionary
        """
        await self.mute_manager.mute_event(event_title, duration_minutes)
        return {
            "muted": True,
            "event": event_title,
            "duration_minutes": duration_minutes,
        }
    
    async def unmute_event(self, event_title: str) -> dict[str, Any]:
        """Unmute an event.
        
        Args:
            event_title: Event to unmute
            
        Returns:
            Result dictionary
        """
        await self.mute_manager.unmute_event(event_title)
        return {"unmuted": True, "event": event_title}
    
    async def mute_sport(
        self,
        sport: str,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Mute alerts for a sport.
        
        Args:
            sport: Sport to mute
            duration_minutes: Duration (None = permanent)
            
        Returns:
            Result dictionary
        """
        await self.mute_manager.mute_sport(sport, duration_minutes)
        return {
            "muted": True,
            "sport": sport,
            "duration_minutes": duration_minutes,
        }
    
    async def unmute_sport(self, sport: str) -> dict[str, Any]:
        """Unmute a sport.
        
        Args:
            sport: Sport to unmute
            
        Returns:
            Result dictionary
        """
        await self.mute_manager.unmute_sport(sport)
        return {"unmuted": True, "sport": sport}
    
    async def unmute_all(self) -> dict[str, Any]:
        """Unmute everything.
        
        Returns:
            Result dictionary
        """
        await self.mute_manager.unmute_all()
        return {"unmuted_all": True}
    
    async def close(self) -> None:
        """Close the bot and cleanup resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Convenience factory function

def create_bot_from_env(
    test_mode: bool | None = None,
) -> TelegramBot:
    """Create a TelegramBot from environment variables.
    
    Args:
        test_mode: Override test mode (if None, use env var)
        
    Returns:
        Configured TelegramBot
    """
    config = TelegramBotConfig.from_env()
    
    if test_mode is not None:
        config.test_mode = test_mode
    
    return TelegramBot(config=config)
