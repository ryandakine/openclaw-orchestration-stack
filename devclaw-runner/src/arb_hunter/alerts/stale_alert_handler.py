"""Handle stale/expired arbitrage opportunities.

Sends follow-up alerts when opportunities disappear.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..arb_opportunity_schema import ArbOpportunity


@dataclass
class TrackedOpportunity:
    """An opportunity being tracked for staleness."""
    
    opportunity: "ArbOpportunity"
    first_seen_at: datetime
    last_seen_at: datetime
    alert_sent: bool = False
    expired_alert_sent: bool = False


class StaleAlertHandler:
    """Tracks opportunities and handles stale/expired alerts.
    
    Monitors when opportunities disappear from the market and sends
    follow-up "expired" alerts to users.
    """
    
    def __init__(self, expiration_minutes: float = 5.0) -> None:
        """Initialize the stale alert handler.
        
        Args:
            expiration_minutes: Minutes before considering an opportunity stale
        """
        self.expiration_minutes = expiration_minutes
        self._tracked: dict[str, TrackedOpportunity] = {}
        self._lock = asyncio.Lock()
    
    async def update_opportunities(
        self,
        current_opportunities: list["ArbOpportunity"],
    ) -> tuple[list["ArbOpportunity"], list[TrackedOpportunity]]:
        """Update tracking with current opportunities.
        
        Args:
            current_opportunities: Currently available opportunities
            
        Returns:
            Tuple of (new_opportunities, expired_opportunities)
        """
        async with self._lock:
            now = datetime.utcnow()
            current_ids = {opp.arb_id for opp in current_opportunities}
            
            # Find new opportunities
            new_opps = [
                opp for opp in current_opportunities
                if opp.arb_id not in self._tracked
            ]
            
            # Find expired opportunities (were tracked but not in current)
            expired_tracked = [
                tracked for arb_id, tracked in self._tracked.items()
                if arb_id not in current_ids
            ]
            
            # Update tracking for current opportunities
            for opp in current_opportunities:
                if opp.arb_id in self._tracked:
                    self._tracked[opp.arb_id].last_seen_at = now
                else:
                    self._tracked[opp.arb_id] = TrackedOpportunity(
                        opportunity=opp,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
            
            # Remove expired from tracking
            for tracked in expired_tracked:
                del self._tracked[tracked.opportunity.arb_id]
            
            return new_opps, expired_tracked
    
    async def mark_alert_sent(self, arb_id: str) -> bool:
        """Mark that an alert was sent for an opportunity.
        
        Args:
            arb_id: The arbitrage opportunity ID
            
        Returns:
            True if marked, False if not found
        """
        async with self._lock:
            if arb_id in self._tracked:
                self._tracked[arb_id].alert_sent = True
                return True
            return False
    
    async def mark_expired_alert_sent(self, arb_id: str) -> bool:
        """Mark that an expired alert was sent.
        
        Args:
            arb_id: The arbitrage opportunity ID
            
        Returns:
            True if marked, False if not found
        """
        async with self._lock:
            if arb_id in self._tracked:
                self._tracked[arb_id].expired_alert_sent = True
                return True
            return False
    
    async def get_expired_for_alerting(
        self,
    ) -> list[TrackedOpportunity]:
        """Get expired opportunities that need alerting.
        
        Only returns opportunities where an alert was sent but
        no expired alert has been sent yet.
        
        Returns:
            List of expired tracked opportunities
        """
        async with self._lock:
            return [
                tracked for tracked in self._tracked.values()
                if tracked.alert_sent
                and not tracked.expired_alert_sent
            ]
    
    def calculate_duration(self, tracked: TrackedOpportunity) -> int:
        """Calculate how long an opportunity was alive.
        
        Args:
            tracked: The tracked opportunity
            
        Returns:
            Duration in seconds
        """
        return int((tracked.last_seen_at - tracked.first_seen_at).total_seconds())
    
    async def cleanup_old(self, max_age_hours: float = 48.0) -> int:
        """Remove very old tracking records.
        
        Args:
            max_age_hours: Maximum age to keep records
            
        Returns:
            Number of records removed
        """
        async with self._lock:
            now = datetime.utcnow()
            old_ids = [
                arb_id for arb_id, tracked in self._tracked.items()
                if (now - tracked.first_seen_at).total_seconds() > max_age_hours * 3600
            ]
            for arb_id in old_ids:
                del self._tracked[arb_id]
            return len(old_ids)
    
    def get_stats(self) -> dict[str, int]:
        """Get handler statistics.
        
        Returns:
            Dictionary with stats
        """
        total = len(self._tracked)
        alerted = sum(1 for t in self._tracked.values() if t.alert_sent)
        expired_alerted = sum(
            1 for t in self._tracked.values() if t.expired_alert_sent
        )
        
        return {
            "total_tracked": total,
            "alerts_sent": alerted,
            "expired_alerts_sent": expired_alerted,
            "pending_expired": alerted - expired_alerted,
        }
