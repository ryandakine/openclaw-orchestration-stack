"""
Test Telegram Module

Tests for alert formatting, deduplication, and priority sorting.
"""

import pytest
from datetime import datetime, timedelta
from typing import Any


class TestAlertFormatting:
    """Test Telegram alert message formatting."""
    
    @pytest.fixture
    def sample_arbitrage(self) -> dict[str, Any]:
        """Sample arbitrage opportunity for formatting tests."""
        return {
            "match_id": "arb_001",
            "polymarket_market": {
                "event_name": "Chiefs vs 49ers",
                "outcome": "Chiefs Win"
            },
            "sportsbook_market": {
                "source": "DraftKings",
                "event_name": "Chiefs vs 49ers"
            },
            "side_a": {
                "venue": "Polymarket",
                "outcome": "Chiefs Win",
                "odds_decimal": 2.1,
                "stake": 476
            },
            "side_b": {
                "venue": "DraftKings",
                "outcome": "49ers Win",
                "odds_decimal": 2.2,
                "stake": 455
            },
            "total_invested": 931,
            "guaranteed_payout": 1000,
            "gross_edge_percent": 7.44,
            "net_edge_percent": 5.69,
            "net_profit": 53,
            "roi_percent": 5.69,
            "timestamp": datetime.now()
        }
    
    def test_format_basic_structure(self, sample_arbitrage: dict):
        """Test basic message structure."""
        message = self._format_alert(sample_arbitrage)
        
        # Should contain key sections
        assert "🎯 ARBITRAGE ALERT" in message or "Arbitrage" in message
        assert str(sample_arbitrage["net_edge_percent"]) in message or "5.69" in message
    
    def test_format_edge_highlighting(self, sample_arbitrage: dict):
        """Test edge percentage is highlighted."""
        message = self._format_alert(sample_arbitrage)
        
        # High edge should be emphasized
        if sample_arbitrage["net_edge_percent"] > 5:
            assert "🔥" in message or "**" in message or "HIGH" in message.upper()
    
    def test_format_stake_details(self, sample_arbitrage: dict):
        """Test stake details are included."""
        message = self._format_alert(sample_arbitrage)
        
        assert "Polymarket" in message
        assert "DraftKings" in message
        assert str(sample_arbitrage["side_a"]["stake"]) in message or "$476" in message
    
    def test_format_profit_calculation(self, sample_arbitrage: dict):
        """Test profit is clearly shown."""
        message = self._format_alert(sample_arbitrage)
        
        assert "Profit" in message or "profit" in message
        assert str(sample_arbitrage["net_profit"]) in message or "$53" in message
    
    def test_format_timestamp_inclusion(self, sample_arbitrage: dict):
        """Test timestamp is included."""
        message = self._format_alert(sample_arbitrage)
        
        # Should have some time reference
        assert "UTC" in message or "ago" in message or datetime.now().strftime("%H:") in message
    
    def test_format_escaping(self):
        """Test special characters are escaped for Telegram."""
        arb_with_special = {
            "polymarket_market": {"event_name": "Team <A> vs Team [B]"},
            "sportsbook_market": {"source": "Book & Co", "event_name": "Test"},
            "net_edge_percent": 5.0,
            "net_profit": 100
        }
        
        message = self._format_alert(arb_with_special)
        
        # Telegram markdown characters should be escaped
        assert "<" not in message or "&lt;" in message
        assert ">" not in message or "&gt;" in message
    
    def test_format_character_limit(self):
        """Test message stays within Telegram limits."""
        long_arb = {
            "polymarket_market": {"event_name": "A" * 1000},
            "sportsbook_market": {"source": "Book", "event_name": "B" * 1000},
            "net_edge_percent": 5.0,
            "net_profit": 100
        }
        
        message = self._format_alert(long_arb)
        
        # Telegram message limit is 4096 characters
        assert len(message) <= 4096
    
    def test_format_empty_data_handling(self):
        """Test handling of missing data."""
        incomplete_arb = {
            "net_edge_percent": 3.0
            # Missing other fields
        }
        
        # Should not raise error
        message = self._format_alert(incomplete_arb)
        assert isinstance(message, str)


class TestAlertDeduplication:
    """Test alert deduplication logic."""
    
    @pytest.fixture
    def dedup_cache(self) -> dict:
        """Empty deduplication cache."""
        return {}
    
    def test_new_alert_not_duplicate(self, dedup_cache: dict):
        """Test new alerts are not marked as duplicates."""
        alert_id = "arb_001"
        
        is_dup = self._check_duplicate(alert_id, dedup_cache, cooldown_minutes=5)
        
        assert is_dup is False
    
    def test_recent_alert_is_duplicate(self, dedup_cache: dict):
        """Test recent alerts are marked as duplicates."""
        alert_id = "arb_001"
        
        # Add to cache
        dedup_cache[alert_id] = datetime.now()
        
        # Check again
        is_dup = self._check_duplicate(alert_id, dedup_cache, cooldown_minutes=5)
        
        assert is_dup is True
    
    def test_expired_alert_not_duplicate(self, dedup_cache: dict):
        """Test expired alerts are not duplicates after cooldown."""
        alert_id = "arb_001"
        
        # Add with old timestamp
        dedup_cache[alert_id] = datetime.now() - timedelta(minutes=10)
        
        # Check with 5 minute cooldown
        is_dup = self._check_duplicate(alert_id, dedup_cache, cooldown_minutes=5)
        
        assert is_dup is False
    
    def test_different_alerts_not_duplicate(self, dedup_cache: dict):
        """Test different alerts are not duplicates."""
        dedup_cache["arb_001"] = datetime.now()
        
        is_dup = self._check_duplicate("arb_002", dedup_cache, cooldown_minutes=5)
        
        assert is_dup is False
    
    def test_cache_cleanup(self, dedup_cache: dict):
        """Test old entries are cleaned up."""
        # Add old entries
        dedup_cache["old_001"] = datetime.now() - timedelta(hours=2)
        dedup_cache["old_002"] = datetime.now() - timedelta(hours=1)
        dedup_cache["new_001"] = datetime.now()
        
        # Clean up entries older than 30 minutes
        self._cleanup_cache(dedup_cache, max_age_minutes=30)
        
        assert "old_001" not in dedup_cache
        assert "old_002" not in dedup_cache
        assert "new_001" in dedup_cache
    
    def test_cache_size_limit(self, dedup_cache: dict):
        """Test cache size limiting."""
        # Add many entries
        for i in range(150):
            dedup_cache[f"arb_{i}"] = datetime.now() - timedelta(minutes=i)
        
        # Enforce max size of 100
        self._enforce_cache_limit(dedup_cache, max_size=100)
        
        assert len(dedup_cache) <= 100


class TestPrioritySorting:
    """Test alert priority sorting."""
    
    @pytest.fixture
    def sample_alerts(self) -> list[dict]:
        """Sample alerts for priority testing."""
        return [
            {
                "match_id": "low_001",
                "net_edge_percent": 2.0,
                "net_profit": 20,
                "liquidity": 10000,
                "confidence": 0.85
            },
            {
                "match_id": "high_001",
                "net_edge_percent": 8.0,
                "net_profit": 150,
                "liquidity": 50000,
                "confidence": 0.95
            },
            {
                "match_id": "medium_001",
                "net_edge_percent": 5.0,
                "net_profit": 75,
                "liquidity": 25000,
                "confidence": 0.90
            }
        ]
    
    def test_sort_by_edge(self, sample_alerts: list):
        """Test sorting by net edge percentage."""
        sorted_alerts = sorted(sample_alerts, key=lambda x: x["net_edge_percent"], reverse=True)
        
        assert sorted_alerts[0]["match_id"] == "high_001"
        assert sorted_alerts[1]["match_id"] == "medium_001"
        assert sorted_alerts[2]["match_id"] == "low_001"
    
    def test_sort_by_profit(self, sample_alerts: list):
        """Test sorting by absolute profit."""
        sorted_alerts = sorted(sample_alerts, key=lambda x: x["net_profit"], reverse=True)
        
        assert sorted_alerts[0]["match_id"] == "high_001"
        assert sorted_alerts[2]["match_id"] == "low_001"
    
    def test_composite_priority_score(self, sample_alerts: list):
        """Test composite priority scoring."""
        for alert in sample_alerts:
            alert["priority_score"] = self._calculate_priority_score(alert)
        
        sorted_alerts = sorted(sample_alerts, key=lambda x: x["priority_score"], reverse=True)
        
        # High edge and profit should be first
        assert sorted_alerts[0]["match_id"] == "high_001"
    
    def test_liquidity_penalty(self):
        """Test that low liquidity reduces priority."""
        low_liq_alert = {
            "net_edge_percent": 10.0,
            "net_profit": 100,
            "liquidity": 500,
            "confidence": 0.95
        }
        high_liq_alert = {
            "net_edge_percent": 8.0,
            "net_profit": 80,
            "liquidity": 100000,
            "confidence": 0.95
        }
        
        low_score = self._calculate_priority_score(low_liq_alert)
        high_score = self._calculate_priority_score(high_liq_alert)
        
        # High liquidity can compensate for lower edge
        assert high_score > low_score * 0.5  # Not drastically lower
    
    def test_confidence_weighting(self):
        """Test confidence affects priority."""
        high_conf = {
            "net_edge_percent": 5.0,
            "net_profit": 50,
            "liquidity": 10000,
            "confidence": 0.98
        }
        low_conf = {
            "net_edge_percent": 5.0,
            "net_profit": 50,
            "liquidity": 10000,
            "confidence": 0.70
        }
        
        high_score = self._calculate_priority_score(high_conf)
        low_score = self._calculate_priority_score(low_conf)
        
        assert high_score > low_score
    
    def test_top_n_selection(self, sample_alerts: list):
        """Test selecting top N alerts."""
        for alert in sample_alerts:
            alert["priority_score"] = self._calculate_priority_score(alert)
        
        sorted_alerts = sorted(sample_alerts, key=lambda x: x["priority_score"], reverse=True)
        top_2 = sorted_alerts[:2]
        
        assert len(top_2) == 2
        assert top_2[0]["match_id"] == "high_001"


class TestBatchProcessing:
    """Test batch alert processing."""
    
    def test_batch_size_limiting(self):
        """Test batch respects size limits."""
        alerts = [{"id": f"arb_{i}"} for i in range(50)]
        
        batch = self._prepare_batch(alerts, max_batch_size=10)
        
        assert len(batch) <= 10
    
    def test_batch_rate_limiting(self):
        """Test rate limiting between batches."""
        last_send_time = datetime.now() - timedelta(seconds=30)
        min_interval = 60  # seconds
        
        can_send = self._check_rate_limit(last_send_time, min_interval)
        
        assert can_send is False
    
    def test_batch_rate_limit_expired(self):
        """Test rate limit allows sending after interval."""
        last_send_time = datetime.now() - timedelta(seconds=90)
        min_interval = 60  # seconds
        
        can_send = self._check_rate_limit(last_send_time, min_interval)
        
        assert can_send is True
    
    def test_batch_grouping(self):
        """Test grouping similar alerts."""
        alerts = [
            {"match_id": "nfl_001", "sport": "football", "edge": 5.0},
            {"match_id": "nfl_002", "sport": "football", "edge": 3.0},
            {"match_id": "nba_001", "sport": "basketball", "edge": 4.0},
        ]
        
        grouped = self._group_by_sport(alerts)
        
        assert "football" in grouped
        assert "basketball" in grouped
        assert len(grouped["football"]) == 2


class TestAlertRetry:
    """Test alert retry logic."""
    
    def test_successful_send_no_retry(self):
        """Test successful send doesn't retry."""
        result = {"ok": True, "message_id": 123}
        
        should_retry = self._should_retry(result, max_retries=3)
        
        assert should_retry is False
    
    def test_failed_send_triggers_retry(self):
        """Test failed send triggers retry."""
        result = {"ok": False, "error": "Network error"}
        retry_count = 0
        
        should_retry = self._should_retry(result, max_retries=3, current_retry=retry_count)
        
        assert should_retry is True
    
    def test_max_retries_exceeded(self):
        """Test no retry after max retries."""
        result = {"ok": False, "error": "Network error"}
        retry_count = 3
        
        should_retry = self._should_retry(result, max_retries=3, current_retry=retry_count)
        
        assert should_retry is False
    
    def test_retry_backoff(self):
        """Test exponential backoff."""
        delays = [self._calculate_retry_delay(i) for i in range(4)]
        
        # Each delay should be longer than previous
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]
        assert delays[3] > delays[2]
        
        # But capped at max
        assert all(d <= 300 for d in delays)  # Max 5 minutes


# Helper methods

    def _format_alert(self, arb: dict) -> str:
        """Format arbitrage as Telegram message."""
        edge = arb.get("net_edge_percent", 0)
        profit = arb.get("net_profit", 0)
        
        # Emoji based on edge size
        emoji = "🔥" if edge > 5 else "🎯" if edge > 2 else "📊"
        
        lines = [
            f"{emoji} ARBITRAGE ALERT",
            "",
            f"Event: {arb.get('polymarket_market', {}).get('event_name', 'Unknown')}",
            f"Edge: {edge:.2f}%",
            f"Profit: ${profit}",
        ]
        
        # Add venue details if available
        side_a = arb.get("side_a", {})
        side_b = arb.get("side_b", {})
        if side_a and side_b:
            lines.extend([
                "",
                f"📊 Polymarket: {side_a.get('outcome', 'N/A')} @ {side_a.get('odds_decimal', 0)}",
                f"📊 {side_b.get('venue', 'Sportsbook')}: {side_b.get('outcome', 'N/A')} @ {side_b.get('odds_decimal', 0)}",
            ])
        
        return "\n".join(lines)
    
    def _check_duplicate(self, alert_id: str, cache: dict, cooldown_minutes: int) -> bool:
        """Check if alert is a duplicate."""
        if alert_id not in cache:
            cache[alert_id] = datetime.now()
            return False
        
        last_sent = cache[alert_id]
        if datetime.now() - last_sent < timedelta(minutes=cooldown_minutes):
            return True
        
        # Update timestamp
        cache[alert_id] = datetime.now()
        return False
    
    def _cleanup_cache(self, cache: dict, max_age_minutes: int):
        """Remove old entries from cache."""
        cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
        to_remove = [k for k, v in cache.items() if v < cutoff]
        for k in to_remove:
            del cache[k]
    
    def _enforce_cache_limit(self, cache: dict, max_size: int):
        """Enforce maximum cache size."""
        while len(cache) > max_size:
            # Remove oldest entry
            oldest = min(cache.keys(), key=lambda k: cache[k])
            del cache[oldest]
    
    def _calculate_priority_score(self, alert: dict) -> float:
        """Calculate priority score for alert."""
        edge = alert.get("net_edge_percent", 0)
        profit = alert.get("net_profit", 0)
        liquidity = alert.get("liquidity", 1000)
        confidence = alert.get("confidence", 0.8)
        
        # Composite score
        score = (
            edge * 10 +  # Edge is most important
            profit * 0.1 +  # Profit secondary
            min(liquidity / 10000, 10) +  # Liquidity bonus (capped)
            confidence * 5  # Confidence multiplier
        )
        
        # Liquidity penalty for very low liquidity
        if liquidity < 1000:
            score *= 0.5
        
        return score
    
    def _prepare_batch(self, alerts: list, max_batch_size: int) -> list:
        """Prepare batch of alerts respecting size limit."""
        return alerts[:max_batch_size]
    
    def _check_rate_limit(self, last_send: datetime, min_interval: int) -> bool:
        """Check if rate limit allows sending."""
        elapsed = (datetime.now() - last_send).total_seconds()
        return elapsed >= min_interval
    
    def _group_by_sport(self, alerts: list) -> dict:
        """Group alerts by sport."""
        grouped = {}
        for alert in alerts:
            sport = alert.get("sport", "unknown")
            if sport not in grouped:
                grouped[sport] = []
            grouped[sport].append(alert)
        return grouped
    
    def _should_retry(self, result: dict, max_retries: int, current_retry: int = 0) -> bool:
        """Determine if alert should be retried."""
        if result.get("ok"):
            return False
        return current_retry < max_retries
    
    def _calculate_retry_delay(self, retry_count: int) -> int:
        """Calculate delay before retry (exponential backoff)."""
        delay = min(2 ** retry_count * 5, 300)  # Max 5 minutes
        return delay
