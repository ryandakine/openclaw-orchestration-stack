"""Rate limiting for Telegram alerts.

Prevents spam by limiting alerts per event, sport, and global rate.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class RateLimitRule:
    """Configuration for a rate limit rule."""
    
    name: str
    window_minutes: int
    max_alerts: int
    description: str = ""


@dataclass
class RateLimitEntry:
    """Entry tracking alert history for rate limiting."""
    
    event_key: str
    first_seen: datetime
    last_alert: datetime
    alert_count: int = 0
    
    def is_expired(self, window_minutes: int) -> bool:
        """Check if entry has expired."""
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        return self.last_alert < cutoff


class AlertRateLimiter:
    """Rate limiter for arbitrage alerts.
    
    Implements multiple rate limiting strategies:
    - Per-event: Max 1 alert per 5 minutes for same event
    - Per-sport: Max N alerts per hour per sport
    - Global: Max N alerts per minute overall
    """
    
    # Default rate limit rules
    DEFAULT_RULES = [
        RateLimitRule(
            name="per_event",
            window_minutes=5,
            max_alerts=1,
            description="Max 1 alert per 5 minutes for same event"
        ),
        RateLimitRule(
            name="per_sport",
            window_minutes=60,
            max_alerts=10,
            description="Max 10 alerts per hour per sport"
        ),
        RateLimitRule(
            name="global",
            window_minutes=1,
            max_alerts=20,
            description="Max 20 alerts per minute overall"
        ),
    ]
    
    def __init__(
        self,
        rules: list[RateLimitRule] | None = None,
        cleanup_interval_minutes: int = 30,
    ):
        """Initialize rate limiter.
        
        Args:
            rules: List of rate limit rules to enforce
            cleanup_interval_minutes: How often to clean up expired entries
        """
        self.rules = rules or self.DEFAULT_RULES.copy()
        self._entries: dict[str, RateLimitEntry] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self._last_cleanup = datetime.utcnow()
    
    def _generate_event_key(
        self,
        event_title: str,
        side_a_venue: str,
        side_b_venue: str,
    ) -> str:
        """Generate unique key for an event.
        
        Creates a hash based on event title and venues to identify
        the same arbitrage opportunity across updates.
        """
        # Normalize for consistent hashing
        normalized = f"{event_title.lower().strip()}:{side_a_venue.lower()}:{side_b_venue.lower()}"
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _generate_sport_key(self, sport: str | None) -> str:
        """Generate key for sport-based limiting."""
        return f"sport:{(sport or 'unknown').lower()}"
    
    def _generate_global_key(self) -> str:
        """Generate key for global limiting."""
        # Global key is time-windowed (per minute)
        now = datetime.utcnow()
        return f"global:{now.strftime('%Y%m%d%H%M')}"
    
    async def check_rate_limit(
        self,
        event_title: str,
        side_a_venue: str,
        side_b_venue: str,
        sport: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Check if alert can be sent based on rate limits.
        
        Args:
            event_title: Event title
            side_a_venue: First venue name
            side_b_venue: Second venue name
            sport: Sport category (optional)
            
        Returns:
            Tuple of (allowed, details dict)
            - allowed: True if alert can be sent
            - details: Information about rate limit status
        """
        async with self._lock:
            # Periodic cleanup
            await self._maybe_cleanup()
            
            details = {
                "allowed": True,
                "rules_checked": [],
                "blocked_by": None,
            }
            
            # Check per-event limit
            event_key = self._generate_event_key(event_title, side_a_venue, side_b_venue)
            event_rule = self._get_rule("per_event")
            if event_rule:
                allowed, reason = self._check_rule(event_key, event_rule)
                details["rules_checked"].append({
                    "rule": "per_event",
                    "allowed": allowed,
                    "reason": reason,
                })
                if not allowed:
                    details["allowed"] = False
                    details["blocked_by"] = "per_event"
                    return False, details
            
            # Check per-sport limit
            if sport:
                sport_key = self._generate_sport_key(sport)
                sport_rule = self._get_rule("per_sport")
                if sport_rule:
                    allowed, reason = self._check_rule(sport_key, sport_rule)
                    details["rules_checked"].append({
                        "rule": "per_sport",
                        "allowed": allowed,
                        "reason": reason,
                    })
                    if not allowed:
                        details["allowed"] = False
                        details["blocked_by"] = "per_sport"
                        return False, details
            
            # Check global limit
            global_key = self._generate_global_key()
            global_rule = self._get_rule("global")
            if global_rule:
                allowed, reason = self._check_rule(global_key, global_rule)
                details["rules_checked"].append({
                    "rule": "global",
                    "allowed": allowed,
                    "reason": reason,
                })
                if not allowed:
                    details["allowed"] = False
                    details["blocked_by"] = "global"
                    return False, details
            
            return True, details
    
    async def record_alert(
        self,
        event_title: str,
        side_a_venue: str,
        side_b_venue: str,
        sport: str | None = None,
    ) -> None:
        """Record that an alert was sent.
        
        Args:
            event_title: Event title
            side_a_venue: First venue name
            side_b_venue: Second venue name
            sport: Sport category (optional)
        """
        async with self._lock:
            now = datetime.utcnow()
            
            # Record per-event
            event_key = self._generate_event_key(event_title, side_a_venue, side_b_venue)
            self._update_entry(event_key, now)
            
            # Record per-sport
            if sport:
                sport_key = self._generate_sport_key(sport)
                self._update_entry(sport_key, now)
            
            # Record global
            global_key = self._generate_global_key()
            self._update_entry(global_key, now)
    
    def _get_rule(self, name: str) -> RateLimitRule | None:
        """Get rule by name."""
        for rule in self.rules:
            if rule.name == name:
                return rule
        return None
    
    def _check_rule(self, key: str, rule: RateLimitRule) -> tuple[bool, str | None]:
        """Check if key passes rate limit rule.
        
        Returns:
            Tuple of (allowed, reason)
        """
        entry = self._entries.get(key)
        
        if entry is None:
            return True, None
        
        if entry.is_expired(rule.window_minutes):
            return True, None
        
        if entry.alert_count >= rule.max_alerts:
            remaining = rule.window_minutes - int(
                (datetime.utcnow() - entry.last_alert).total_seconds() / 60
            )
            return False, f"Rate limited: {rule.name} ({remaining}m remaining)"
        
        return True, None
    
    def _update_entry(self, key: str, now: datetime) -> None:
        """Update or create rate limit entry."""
        if key in self._entries:
            entry = self._entries[key]
            entry.last_alert = now
            entry.alert_count += 1
        else:
            self._entries[key] = RateLimitEntry(
                event_key=key,
                first_seen=now,
                last_alert=now,
                alert_count=1,
            )
    
    async def _maybe_cleanup(self) -> None:
        """Clean up expired entries if interval has passed."""
        now = datetime.utcnow()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        # Find max window across all rules
        max_window = max(rule.window_minutes for rule in self.rules) if self.rules else 60
        cutoff = now - timedelta(minutes=max_window * 2)  # Keep 2x window for safety
        
        expired = [
            key for key, entry in self._entries.items()
            if entry.last_alert < cutoff
        ]
        
        for key in expired:
            del self._entries[key]
        
        self._last_cleanup = now
    
    async def force_cleanup(self) -> int:
        """Force immediate cleanup of all expired entries.
        
        Returns:
            Number of entries removed
        """
        async with self._lock:
            max_window = max(rule.window_minutes for rule in self.rules) if self.rules else 60
            cutoff = datetime.utcnow() - timedelta(minutes=max_window * 2)
            
            expired = [
                key for key, entry in self._entries.items()
                if entry.last_alert < cutoff
            ]
            
            for key in expired:
                del self._entries[key]
            
            self._last_cleanup = datetime.utcnow()
            return len(expired)
    
    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status.
        
        Returns:
            Dictionary with status information
        """
        now = datetime.utcnow()
        
        status = {
            "total_entries": len(self._entries),
            "rules": [],
            "by_rule": {},
        }
        
        for rule in self.rules:
            rule_status = {
                "name": rule.name,
                "window_minutes": rule.window_minutes,
                "max_alerts": rule.max_alerts,
            }
            
            # Count active entries for this rule's window
            cutoff = now - timedelta(minutes=rule.window_minutes)
            active = sum(
                1 for entry in self._entries.values()
                if entry.last_alert >= cutoff
            )
            
            rule_status["active_entries"] = active
            status["rules"].append(rule_status)
        
        return status
    
    def reset(self) -> None:
        """Clear all rate limit entries."""
        self._entries.clear()


class MuteManager:
    """Manages mute settings for events and sports.
    
    Allows users to temporarily disable alerts for specific
    events, sports, or venues.
    """
    
    def __init__(self):
        """Initialize mute manager."""
        self._muted_events: set[str] = set()
        self._muted_sports: set[str] = set()
        self._muted_venues: set[str] = set()
        self._temp_mutes: dict[str, datetime] = {}  # key -> unmute time
        self._lock = asyncio.Lock()
    
    async def mute_event(self, event_title: str, duration_minutes: int | None = None) -> None:
        """Mute alerts for a specific event.
        
        Args:
            event_title: Event to mute
            duration_minutes: Duration to mute (None = permanent)
        """
        async with self._lock:
            key = event_title.lower().strip()
            self._muted_events.add(key)
            
            if duration_minutes:
                self._temp_mutes[f"event:{key}"] = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    async def unmute_event(self, event_title: str) -> None:
        """Unmute a specific event."""
        async with self._lock:
            key = event_title.lower().strip()
            self._muted_events.discard(key)
            self._temp_mutes.pop(f"event:{key}", None)
    
    async def mute_sport(self, sport: str, duration_minutes: int | None = None) -> None:
        """Mute alerts for a sport.
        
        Args:
            sport: Sport to mute
            duration_minutes: Duration to mute (None = permanent)
        """
        async with self._lock:
            key = sport.lower().strip()
            self._muted_sports.add(key)
            
            if duration_minutes:
                self._temp_mutes[f"sport:{key}"] = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    async def unmute_sport(self, sport: str) -> None:
        """Unmute a sport."""
        async with self._lock:
            key = sport.lower().strip()
            self._muted_sports.discard(key)
            self._temp_mutes.pop(f"sport:{key}", None)
    
    async def mute_venue(self, venue: str, duration_minutes: int | None = None) -> None:
        """Mute alerts involving a specific venue.
        
        Args:
            venue: Venue to mute
            duration_minutes: Duration to mute (None = permanent)
        """
        async with self._lock:
            key = venue.lower().strip()
            self._muted_venues.add(key)
            
            if duration_minutes:
                self._temp_mutes[f"venue:{key}"] = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    async def unmute_venue(self, venue: str) -> None:
        """Unmute a venue."""
        async with self._lock:
            key = venue.lower().strip()
            self._muted_venues.discard(key)
            self._temp_mutes.pop(f"venue:{key}", None)
    
    async def is_muted(
        self,
        event_title: str,
        side_a_venue: str,
        side_b_venue: str,
        sport: str | None = None,
    ) -> tuple[bool, str | None]:
        """Check if an alert should be muted.
        
        Returns:
            Tuple of (is_muted, reason)
        """
        async with self._lock:
            await self._cleanup_temp_mutes()
            
            event_key = event_title.lower().strip()
            if event_key in self._muted_events:
                return True, f"Event '{event_title}' is muted"
            
            if sport:
                sport_key = sport.lower().strip()
                if sport_key in self._muted_sports:
                    return True, f"Sport '{sport}' is muted"
            
            venue_a_key = side_a_venue.lower().strip()
            venue_b_key = side_b_venue.lower().strip()
            if venue_a_key in self._muted_venues:
                return True, f"Venue '{side_a_venue}' is muted"
            if venue_b_key in self._muted_venues:
                return True, f"Venue '{side_b_venue}' is muted"
            
            return False, None
    
    async def get_muted_items(self) -> dict[str, list[str]]:
        """Get all currently muted items."""
        async with self._lock:
            await self._cleanup_temp_mutes()
            
            return {
                "events": sorted(self._muted_events),
                "sports": sorted(self._muted_sports),
                "venues": sorted(self._muted_venues),
            }
    
    async def unmute_all(self) -> None:
        """Unmute everything."""
        async with self._lock:
            self._muted_events.clear()
            self._muted_sports.clear()
            self._muted_venues.clear()
            self._temp_mutes.clear()
    
    async def _cleanup_temp_mutes(self) -> None:
        """Remove expired temporary mutes."""
        now = datetime.utcnow()
        expired = [
            key for key, unmute_time in self._temp_mutes.items()
            if now >= unmute_time
        ]
        
        for key in expired:
            del self._temp_mutes[key]
            
            # Remove from appropriate set
            if key.startswith("event:"):
                self._muted_events.discard(key[6:])
            elif key.startswith("sport:"):
                self._muted_sports.discard(key[6:])
            elif key.startswith("venue:"):
                self._muted_venues.discard(key[6:])
