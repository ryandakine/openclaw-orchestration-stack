"""Tests for the Telegram notification system.

Tests formatter, rate limiter, history, and bot integration.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Import the notification modules
from src.arb_hunter.notifications.formatter import (
    AlertFormatter,
    format_opportunity_alert,
    _escape_markdown,
    FormattedAlert,
)
from src.arb_hunter.notifications.ratelimiter import (
    AlertRateLimiter,
    MuteManager,
    RateLimitRule,
)
from src.arb_hunter.notifications.history import (
    AlertHistory,
    AlertRecord,
)
from src.arb_hunter.notifications.telegram_bot import (
    TelegramBot,
    TelegramBotConfig,
    create_bot_from_env,
)


class TestMessageFormatter:
    """Test alert message formatting."""
    
    def test_escape_markdown(self):
        """Test markdown escaping."""
        assert _escape_markdown("test_text") == "test\\_text"
        assert _escape_markdown("test*text") == "test\\*text"
        assert _escape_markdown("[link]") == "\\[link\\]"
    
    def test_format_opportunity_alert_basic(self):
        """Test basic alert formatting."""
        message = format_opportunity_alert(
            event_title="Lakers vs Warriors",
            side_a_venue="DraftKings",
            side_a_outcome="Lakers",
            side_a_odds=2.10,
            side_b_venue="Polymarket",
            side_b_outcome="Warriors",
            side_b_odds=2.05,
            profit_pct=0.032,
            total_stake=1000.0,
            side_a_stake=512.0,
            side_b_stake=488.0,
        )
        
        # Check structure
        assert "ARBITRAGE OPPORTUNITY" in message
        assert "Lakers vs Warriors" in message
        assert "DraftKings" in message
        assert "Polymarket" in message
        assert "3.20%" in message or "3.2%" in message
        assert "$1,000.00" in message or "$1000" in message
    
    def test_format_opportunity_alert_with_times(self):
        """Test alert with start time and expiry."""
        start_time = datetime.utcnow() + timedelta(hours=5)
        
        message = format_opportunity_alert(
            event_title="Chiefs vs 49ers",
            side_a_venue="FanDuel",
            side_a_outcome="Chiefs",
            side_a_odds=1.95,
            side_b_venue="Polymarket",
            side_b_outcome="49ers",
            side_b_odds=2.15,
            profit_pct=0.05,
            total_stake=2000.0,
            side_a_stake=1000.0,
            side_b_stake=1000.0,
            start_time=start_time,
            expires_minutes=45,
        )
        
        assert "Start:" in message
        assert "Expires in:" in message
        assert "45 minutes" in message
    
    def test_format_with_special_characters(self):
        """Test handling of special characters in event names."""
        message = format_opportunity_alert(
            event_title="Team <A> vs Team [B] (Live)",
            side_a_venue="Book & Co",
            side_a_outcome="Team <A>",
            side_a_odds=2.0,
            side_b_venue="Market_Pro",
            side_b_outcome="Team [B]",
            side_b_odds=2.1,
            profit_pct=0.025,
            total_stake=500.0,
            side_a_stake=250.0,
            side_b_stake=250.0,
        )
        
        # Telegram markdown characters should be escaped
        # Just verify it doesn't crash and creates output
        assert isinstance(message, str)
        assert len(message) > 0
    
    def test_profit_emoji_selection(self):
        """Test emoji selection based on profit."""
        # High profit
        msg_high = format_opportunity_alert(
            event_title="High Profit Event",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.06,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        assert "🔥" in msg_high
        
        # Medium profit
        msg_med = format_opportunity_alert(
            event_title="Medium Profit Event",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.03,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        assert "🚀" in msg_med
    
    def test_message_character_limit(self):
        """Test message stays within Telegram limits."""
        long_name = "A" * 5000
        
        message = format_opportunity_alert(
            event_title=long_name,
            side_a_venue="Venue",
            side_a_outcome="Outcome",
            side_a_odds=2.0,
            side_b_venue="Venue2",
            side_b_outcome="Outcome2",
            side_b_odds=2.1,
            profit_pct=0.02,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        # Telegram message limit is 4096 characters
        assert len(message) <= 4096


class TestAlertFormatter:
    """Test AlertFormatter class."""
    
    def test_format_system_alert(self):
        """Test system alert formatting."""
        formatter = AlertFormatter()
        
        alert = formatter.format_system_alert(
            alert_type="error",
            message="Connection failed",
            details={"retry": 3, "endpoint": "/api"},
        )
        
        assert "ERROR" in alert.message.upper()
        assert "Connection failed" in alert.message
        assert alert.priority == 10
        assert alert.event_id == "system_error"
    
    def test_format_system_alert_startup(self):
        """Test startup alert formatting."""
        formatter = AlertFormatter()
        
        alert = formatter.format_system_alert(
            alert_type="startup",
            message="System started successfully",
        )
        
        assert "🚀" in alert.message
        assert alert.priority == 5
    
    def test_priority_calculation(self):
        """Test priority scoring."""
        formatter = AlertFormatter()
        
        # High profit, high size
        p1 = formatter._calculate_priority(0.06, 15000)
        assert p1 >= 8
        
        # Low profit, low size
        p2 = formatter._calculate_priority(0.01, 1000)
        assert p2 <= 6
        
        # Medium values
        p3 = formatter._calculate_priority(0.03, 7500)
        assert 6 <= p3 <= 8


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a test rate limiter."""
        return AlertRateLimiter()
    
    @pytest.mark.asyncio
    async def test_first_alert_allowed(self, rate_limiter):
        """Test first alert is always allowed."""
        allowed, details = await rate_limiter.check_rate_limit(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
            sport="basketball",
        )
        
        assert allowed is True
        assert details["allowed"] is True
    
    @pytest.mark.asyncio
    async def test_duplicate_blocked(self, rate_limiter):
        """Test duplicate alerts are blocked."""
        # First alert
        await rate_limiter.record_alert(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
            sport="basketball",
        )
        
        # Immediate duplicate
        allowed, details = await rate_limiter.check_rate_limit(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
            sport="basketball",
        )
        
        assert allowed is False
        assert details["blocked_by"] == "per_event"
    
    @pytest.mark.asyncio
    async def test_different_event_allowed(self, rate_limiter):
        """Test different events are allowed."""
        # First alert
        await rate_limiter.record_alert(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
            sport="basketball",
        )
        
        # Different event
        allowed, details = await rate_limiter.check_rate_limit(
            "Chiefs vs 49ers",
            "FanDuel",
            "Kalshi",
            sport="football",
        )
        
        assert allowed is True
    
    def test_custom_rules(self):
        """Test custom rate limit rules."""
        custom_rules = [
            RateLimitRule(
                name="per_event",
                window_minutes=1,
                max_alerts=1,
            ),
        ]
        
        limiter = AlertRateLimiter(rules=custom_rules)
        assert len(limiter.rules) == 1
        assert limiter.rules[0].window_minutes == 1
    
    def test_get_status(self, rate_limiter):
        """Test status reporting."""
        status = rate_limiter.get_status()
        
        assert "total_entries" in status
        assert "rules" in status
        assert len(status["rules"]) == 3  # default rules


class TestMuteManager:
    """Test mute functionality."""
    
    @pytest.fixture
    def mute_manager(self):
        """Create a test mute manager."""
        return MuteManager()
    
    @pytest.mark.asyncio
    async def test_mute_event(self, mute_manager):
        """Test muting an event."""
        await mute_manager.mute_event("Lakers vs Warriors")
        
        is_muted, reason = await mute_manager.is_muted(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
        )
        
        assert is_muted is True
        assert "Lakers vs Warriors" in reason
    
    @pytest.mark.asyncio
    async def test_mute_sport(self, mute_manager):
        """Test muting a sport."""
        await mute_manager.mute_sport("basketball")
        
        is_muted, reason = await mute_manager.is_muted(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
            sport="basketball",
        )
        
        assert is_muted is True
        assert "basketball" in reason
    
    @pytest.mark.asyncio
    async def test_mute_venue(self, mute_manager):
        """Test muting a venue."""
        await mute_manager.mute_venue("DraftKings")
        
        is_muted, reason = await mute_manager.is_muted(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
        )
        
        assert is_muted is True
        assert "DraftKings" in reason
    
    @pytest.mark.asyncio
    async def test_unmute(self, mute_manager):
        """Test unmuting."""
        await mute_manager.mute_event("Lakers vs Warriors")
        await mute_manager.unmute_event("Lakers vs Warriors")
        
        is_muted, _ = await mute_manager.is_muted(
            "Lakers vs Warriors",
            "DraftKings",
            "Polymarket",
        )
        
        assert is_muted is False
    
    @pytest.mark.asyncio
    async def test_get_muted_items(self, mute_manager):
        """Test listing muted items."""
        await mute_manager.mute_event("Event 1")
        await mute_manager.mute_sport("football")
        await mute_manager.mute_venue("FanDuel")
        
        muted = await mute_manager.get_muted_items()
        
        assert "event 1" in muted["events"]
        assert "football" in muted["sports"]
        assert "fanduel" in muted["venues"]
    
    @pytest.mark.asyncio
    async def test_unmute_all(self, mute_manager):
        """Test unmute all."""
        await mute_manager.mute_event("Event 1")
        await mute_manager.mute_sport("football")
        
        await mute_manager.unmute_all()
        
        muted = await mute_manager.get_muted_items()
        
        assert len(muted["events"]) == 0
        assert len(muted["sports"]) == 0
    
    @pytest.mark.asyncio
    async def test_temporary_mute(self, mute_manager):
        """Test temporary mute expires."""
        # Mute for 0 minutes (immediate expiration on cleanup)
        await mute_manager.mute_event("Temp Event", duration_minutes=0)
        
        # Force cleanup of expired mutes
        await mute_manager._cleanup_temp_mutes()
        
        is_muted, _ = await mute_manager.is_muted(
            "Temp Event",
            "Venue A",
            "Venue B",
        )
        
        # Should be unmuted after cleanup
        assert is_muted is False


class TestAlertHistory:
    """Test alert history tracking."""
    
    @pytest.fixture
    async def history(self):
        """Create a test history with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist = AlertHistory(history_dir=tmpdir, auto_save=False)
            yield hist
    
    @pytest.mark.asyncio
    async def test_record_alert(self, history):
        """Test recording an alert."""
        record = await history.record(
            alert_id="test_001",
            event_title="Lakers vs Warriors",
            message="Test message",
            profit_pct=0.05,
            sport="basketball",
            venues=["DraftKings", "Polymarket"],
        )
        
        assert record.alert_id == "test_001"
        assert record.event_title == "Lakers vs Warriors"
        assert record.sport == "basketball"
    
    @pytest.mark.asyncio
    async def test_get_recent(self, history):
        """Test retrieving recent alerts."""
        await history.record(
            alert_id="recent_001",
            event_title="Recent Event",
            message="Test",
            profit_pct=0.05,
        )
        
        recent = await history.get_recent(hours=24)
        
        assert len(recent) >= 1
        assert any(r.alert_id == "recent_001" for r in recent)
    
    @pytest.mark.asyncio
    async def test_get_stats(self, history):
        """Test statistics generation."""
        await history.record(
            alert_id="stat_001",
            event_title="Event 1",
            message="Test",
            profit_pct=0.05,
            sport="basketball",
            success=True,
        )
        await history.record(
            alert_id="stat_002",
            event_title="Event 2",
            message="Test",
            profit_pct=0.03,
            sport="football",
            success=False,
            error_message="Failed",
        )
        
        stats = await history.get_stats(days=7)
        
        assert stats["total_alerts"] >= 2
        assert stats["successful"] >= 1
        assert stats["failed"] >= 1
        assert "basketball" in stats["total_by_sport"] or "football" in stats["total_by_sport"]
    
    @pytest.mark.asyncio
    async def test_was_recently_sent(self, history):
        """Test checking for recent duplicates."""
        await history.record(
            alert_id="dup_001",
            event_title="Duplicate Check Event",
            message="Test",
            profit_pct=0.05,
        )
        
        was_sent = await history.was_recently_sent(
            "Duplicate Check Event",
            minutes=5,
        )
        
        assert was_sent is True
    
    @pytest.mark.asyncio
    async def test_save_and_load(self, history):
        """Test persistence."""
        await history.record(
            alert_id="persist_001",
            event_title="Persistent Event",
            message="Test",
            profit_pct=0.05,
        )
        
        await history.save()
        
        # Create new history pointing to same dir
        history2 = AlertHistory(history_dir=history.history_dir, auto_save=False)
        await history2.load()
        
        found = await history2.find_by_event("Persistent Event")
        
        assert len(found) >= 1
        assert found[0].alert_id == "persist_001"


class TestTelegramBot:
    """Test TelegramBot integration."""
    
    @pytest.fixture
    def bot(self):
        """Create a test bot in test mode."""
        config = TelegramBotConfig(
            bot_token="test_token",
            chat_id="test_chat",
            test_mode=True,
            enabled=True,
        )
        return TelegramBot(config=config)
    
    @pytest.mark.asyncio
    async def test_send_opportunity_alert(self, bot):
        """Test sending an opportunity alert in test mode."""
        result = await bot.send_opportunity_alert(
            event_title="Lakers vs Warriors",
            side_a_venue="DraftKings",
            side_a_outcome="Lakers",
            side_a_odds=2.10,
            side_b_venue="Polymarket",
            side_b_outcome="Warriors",
            side_b_odds=2.05,
            profit_pct=0.032,
            total_stake=1000.0,
            side_a_stake=512.0,
            side_b_stake=488.0,
            alert_id="test_alert_001",
            sport="basketball",
        )
        
        assert result["sent"] is True
        assert result["test_mode"] is True
        assert result["alert_id"] == "test_alert_001"
    
    @pytest.mark.asyncio
    async def test_min_profit_threshold(self, bot):
        """Test minimum profit threshold."""
        bot.config.min_profit_alert_pct = 0.05  # 5%
        
        result = await bot.send_opportunity_alert(
            event_title="Low Profit Event",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.01,  # 1% - below threshold
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        assert result["sent"] is False
        assert "below threshold" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_muted_event(self, bot):
        """Test muted events are not sent."""
        await bot.mute_event("Muted Event")
        
        result = await bot.send_opportunity_alert(
            event_title="Muted Event",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.05,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        assert result["sent"] is False
        assert "Muted" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_send_system_alert(self, bot):
        """Test system alerts."""
        result = await bot.send_system_alert(
            alert_type="startup",
            message="System initialized",
            details={"version": "1.0.0"},
        )
        
        assert result["sent"] is True
    
    @pytest.mark.asyncio
    async def test_get_stats(self, bot):
        """Test getting bot stats."""
        # Send some alerts first
        await bot.send_opportunity_alert(
            event_title="Stats Test Event",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.05,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        stats = await bot.get_stats(days=7)
        
        assert "history" in stats
        assert "rate_limiter" in stats
        assert "muted" in stats
        assert "config" in stats
    
    @pytest.mark.asyncio
    async def test_mute_and_unmute(self, bot):
        """Test mute/unmute operations."""
        mute_result = await bot.mute_event("Test Event", duration_minutes=60)
        assert mute_result["muted"] is True
        
        unmute_result = await bot.unmute_event("Test Event")
        assert unmute_result["unmuted"] is True
    
    @pytest.mark.asyncio
    async def test_test_connection(self, bot):
        """Test connection check in test mode."""
        result = await bot.test_connection()
        
        assert result["connected"] is True
        assert result["test_mode"] is True


class TestBotConfig:
    """Test TelegramBotConfig."""
    
    def test_from_env_defaults(self, monkeypatch):
        """Test config from environment with defaults."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_TEST_MODE", "false")
        
        config = TelegramBotConfig.from_env()
        
        assert config.bot_token == "test_token"
        assert config.chat_id == "12345"
        assert config.enabled is True
        assert config.test_mode is False
        assert config.min_profit_alert_pct == 0.01
    
    def test_from_env_custom(self, monkeypatch):
        """Test config from environment with custom values."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "custom_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "67890")
        monkeypatch.setenv("TELEGRAM_MIN_PROFIT_PCT", "0.05")
        monkeypatch.setenv("TELEGRAM_TEST_MODE", "true")
        
        config = TelegramBotConfig.from_env()
        
        assert config.min_profit_alert_pct == 0.05
        assert config.test_mode is True


class TestIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_full_alert_flow(self):
        """Test complete alert flow from format to history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create bot with all components
            config = TelegramBotConfig(
                bot_token="test",
                chat_id="test",
                test_mode=True,
                history_dir=tmpdir,
            )
            
            bot = TelegramBot(config=config)
            
            # Send alert
            result = await bot.send_opportunity_alert(
                event_title="Integration Test",
                side_a_venue="DraftKings",
                side_a_outcome="Lakers",
                side_a_odds=2.10,
                side_b_venue="Polymarket",
                side_b_outcome="Warriors",
                side_b_odds=2.05,
                profit_pct=0.032,
                total_stake=1000.0,
                side_a_stake=512.0,
                side_b_stake=488.0,
                sport="basketball",
            )
            
            assert result["sent"] is True
            
            # Check history
            stats = await bot.get_stats(days=1)
            assert stats["history"]["total_alerts"] >= 1
            
            # Check rate limiter recorded it
            rate_status = bot.rate_limiter.get_status()
            assert rate_status["total_entries"] > 0
    
    @pytest.mark.asyncio
    async def test_rate_limit_prevents_duplicate(self):
        """Test rate limiting prevents duplicate alerts."""
        config = TelegramBotConfig(
            bot_token="test",
            chat_id="test",
            test_mode=True,
        )
        
        bot = TelegramBot(config=config)
        
        # First alert
        result1 = await bot.send_opportunity_alert(
            event_title="Rate Limit Test",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.05,
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        # Immediate duplicate should be blocked
        result2 = await bot.send_opportunity_alert(
            event_title="Rate Limit Test",
            side_a_venue="A",
            side_a_outcome="X",
            side_a_odds=2.0,
            side_b_venue="B",
            side_b_outcome="Y",
            side_b_odds=2.0,
            profit_pct=0.06,  # Even higher profit
            total_stake=100.0,
            side_a_stake=50.0,
            side_b_stake=50.0,
        )
        
        assert result1["sent"] is True
        assert result2["sent"] is False
        assert "Rate limited" in result2["reason"]
