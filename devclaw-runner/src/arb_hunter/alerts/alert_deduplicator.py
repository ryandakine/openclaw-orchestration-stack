"""Alert deduplication logic.

Prevents sending duplicate alerts for the same opportunity within a time window.
Re-sends if the edge changes significantly (> 1%).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..arb_opportunity_schema import ArbOpportunity


@dataclass
class SentAlertRecord:
    """Record of a sent alert."""
    
    arb_id: str
    net_edge_pct: float
    sent_at: datetime
    expected_profit: float


class AlertDeduplicator:
    """Deduplicates alerts to prevent spam.
    
    Tracks sent alerts by arb_id and prevents re-sending within 24 hours
    unless the edge changes by more than 1%.
    """
    
    DEFAULT_COOLDOWN_HOURS = 24
    DEFAULT_EDGE_CHANGE_THRESHOLD = 0.01  # 1%
    
    def __init__(
        self,
        cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
        edge_change_threshold: float = DEFAULT_EDGE_CHANGE_THRESHOLD,
    ) -> None:
        """Initialize the deduplicator.
        
        Args:
            cooldown_hours: Minimum hours before re-sending
            edge_change_threshold: Minimum edge change (as decimal) to re-send
        """
        self.cooldown_hours = cooldown_hours
        self.edge_change_threshold = edge_change_threshold
        self._sent_alerts: dict[str, SentAlertRecord] = {}
        self._lock = asyncio.Lock()
    
    async def should_send(
        self,
        opportunity: "ArbOpportunity",
    ) -> tuple[bool, str]:
        """Check if an alert should be sent.
        
        Args:
            opportunity: The arbitrage opportunity to check
            
        Returns:
            Tuple of (should_send, reason)
        """
        async with self._lock:
            arb_id = opportunity.arb_id
            now = datetime.utcnow()
            
            # Check if we've sent this alert before
            if arb_id not in self._sent_alerts:
                return True, "New opportunity"
            
            record = self._sent_alerts[arb_id]
            
            # Check if cooldown has expired
            cooldown_expires = record.sent_at + timedelta(hours=self.cooldown_hours)
            if now >= cooldown_expires:
                return True, f"Cooldown expired ({self.cooldown_hours}h)"
            
            # Check if edge has changed significantly
            edge_diff = abs(opportunity.net_edge_pct - record.net_edge_pct)
            if edge_diff >= self.edge_change_threshold:
                return (
                    True,
                    f"Edge changed significantly ({edge_diff*100:.1f}%)"
                )
            
            # Check if profit has changed significantly (> 20%)
            if record.expected_profit > 0:
                profit_diff = abs(
                    opportunity.expected_profit - record.expected_profit
                )
                profit_change_pct = profit_diff / record.expected_profit
                if profit_change_pct >= 0.20:
                    return (
                        True,
                        f"Profit changed significantly ({profit_change_pct*100:.0f}%)"
                    )
            
            # Don't send - no significant changes
            time_remaining = cooldown_expires - now
            return (
                False,
                f"Recently sent ({time_remaining.total_seconds()/3600:.1f}h remaining)"
            )
    
    async def record_sent(self, opportunity: "ArbOpportunity") -> None:
        """Record that an alert was sent.
        
        Args:
            opportunity: The opportunity that was alerted
        """
        async with self._lock:
            self._sent_alerts[opportunity.arb_id] = SentAlertRecord(
                arb_id=opportunity.arb_id,
                net_edge_pct=opportunity.net_edge_pct,
                sent_at=datetime.utcnow(),
                expected_profit=opportunity.expected_profit,
            )
    
    async def remove_record(self, arb_id: str) -> bool:
        """Remove a record from the deduplication cache.
        
        Args:
            arb_id: The arbitrage ID to remove
            
        Returns:
            True if record was removed, False if not found
        """
        async with self._lock:
            if arb_id in self._sent_alerts:
                del self._sent_alerts[arb_id]
                return True
            return False
    
    async def get_record(self, arb_id: str) -> SentAlertRecord | None:
        """Get a sent alert record.
        
        Args:
            arb_id: The arbitrage ID to look up
            
        Returns:
            SentAlertRecord if found, None otherwise
        """
        async with self._lock:
            return self._sent_alerts.get(arb_id)
    
    async def cleanup_expired(self) -> int:
        """Remove expired records from the cache.
        
        Returns:
            Number of records removed
        """
        async with self._lock:
            now = datetime.utcnow()
            expired_ids = [
                arb_id for arb_id, record in self._sent_alerts.items()
                if now >= record.sent_at + timedelta(hours=self.cooldown_hours)
            ]
            for arb_id in expired_ids:
                del self._sent_alerts[arb_id]
            return len(expired_ids)
    
    def get_stats(self) -> dict[str, int]:
        """Get deduplicator statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            "total_tracked": len(self._sent_alerts),
            "cooldown_hours": self.cooldown_hours,
            "edge_threshold_pct": int(self.edge_change_threshold * 100),
        }
