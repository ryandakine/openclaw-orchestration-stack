"""Alert history tracking for Telegram notifications.

Stores sent alerts to disk for auditing, analysis, and deduplication.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class AlertRecord:
    """Record of a sent alert."""
    
    alert_id: str
    event_title: str
    message: str
    sent_at: datetime
    profit_pct: float
    sport: str | None = None
    venues: list[str] = field(default_factory=list)
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "event_title": self.event_title,
            "message": self.message,
            "sent_at": self.sent_at.isoformat(),
            "profit_pct": self.profit_pct,
            "sport": self.sport,
            "venues": self.venues,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertRecord:
        """Create from dictionary."""
        return cls(
            alert_id=data["alert_id"],
            event_title=data["event_title"],
            message=data["message"],
            sent_at=datetime.fromisoformat(data["sent_at"]),
            profit_pct=data["profit_pct"],
            sport=data.get("sport"),
            venues=data.get("venues", []),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class AlertHistory:
    """Manages history of sent alerts.
    
    Provides persistence, querying, and statistics for alerts.
    """
    
    def __init__(
        self,
        history_dir: str | Path | None = None,
        max_days: int = 30,
        auto_save: bool = True,
    ):
        """Initialize alert history.
        
        Args:
            history_dir: Directory to store history files (default: data/alerts/)
            max_days: Maximum days to keep history
            auto_save: Whether to auto-save after each record
        """
        if history_dir is None:
            # Default to project data directory
            project_root = Path(__file__).parent.parent.parent.parent.parent
            history_dir = project_root / "data" / "alerts"
        
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_days = max_days
        self.auto_save = auto_save
        
        self._records: list[AlertRecord] = []
        self._lock = asyncio.Lock()
        self._loaded = False
    
    async def _ensure_loaded(self) -> None:
        """Load history if not already loaded."""
        if not self._loaded:
            await self.load()
            self._loaded = True
    
    async def record(
        self,
        alert_id: str,
        event_title: str,
        message: str,
        profit_pct: float,
        sport: str | None = None,
        venues: list[str] | None = None,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AlertRecord:
        """Record a sent alert.
        
        Args:
            alert_id: Unique alert identifier
            event_title: Event title
            message: Full message text
            profit_pct: Profit percentage
            sport: Sport category
            venues: List of venues involved
            success: Whether send was successful
            error_message: Error message if failed
            metadata: Additional metadata
            
        Returns:
            Created AlertRecord
        """
        await self._ensure_loaded()
        
        record = AlertRecord(
            alert_id=alert_id,
            event_title=event_title,
            message=message,
            sent_at=datetime.utcnow(),
            profit_pct=profit_pct,
            sport=sport,
            venues=venues or [],
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._records.append(record)
            
            # Enforce max size limit (keep last 10k records in memory)
            if len(self._records) > 10000:
                self._records = self._records[-10000:]
        
        if self.auto_save:
            await self.save()
        
        return record
    
    async def get_recent(
        self,
        hours: int = 24,
        sport: str | None = None,
        min_profit: float | None = None,
    ) -> list[AlertRecord]:
        """Get recent alerts.
        
        Args:
            hours: Number of hours to look back
            sport: Filter by sport (optional)
            min_profit: Minimum profit percentage (optional)
            
        Returns:
            List of matching records
        """
        await self._ensure_loaded()
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        async with self._lock:
            results = [
                r for r in self._records
                if r.sent_at >= cutoff
                and (sport is None or r.sport == sport)
                and (min_profit is None or r.profit_pct >= min_profit)
            ]
        
        return results
    
    async def get_stats(self, days: int = 7) -> dict[str, Any]:
        """Get alert statistics.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with statistics
        """
        await self._ensure_loaded()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        async with self._lock:
            recent = [r for r in self._records if r.sent_at >= cutoff]
        
        if not recent:
            return {
                "total_alerts": 0,
                "successful": 0,
                "failed": 0,
                "avg_profit_pct": 0.0,
                "total_by_sport": {},
                "period_days": days,
            }
        
        total = len(recent)
        successful = sum(1 for r in recent if r.success)
        failed = total - successful
        avg_profit = sum(r.profit_pct for r in recent) / total
        
        # Count by sport
        by_sport: dict[str, int] = {}
        for r in recent:
            sport = r.sport or "unknown"
            by_sport[sport] = by_sport.get(sport, 0) + 1
        
        return {
            "total_alerts": total,
            "successful": successful,
            "failed": failed,
            "avg_profit_pct": round(avg_profit, 4),
            "total_by_sport": by_sport,
            "period_days": days,
        }
    
    async def was_recently_sent(
        self,
        event_title: str,
        minutes: int = 5,
    ) -> bool:
        """Check if alert was sent recently for an event.
        
        Args:
            event_title: Event title to check
            minutes: Time window to check
            
        Returns:
            True if alert was sent recently
        """
        await self._ensure_loaded()
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        event_lower = event_title.lower().strip()
        
        async with self._lock:
            for r in self._records:
                if r.sent_at >= cutoff and r.event_title.lower().strip() == event_lower:
                    return True
        
        return False
    
    async def find_by_event(self, event_title: str) -> list[AlertRecord]:
        """Find all alerts for an event.
        
        Args:
            event_title: Event title to search
            
        Returns:
            List of matching records
        """
        await self._ensure_loaded()
        
        event_lower = event_title.lower().strip()
        
        async with self._lock:
            return [
                r for r in self._records
                if r.event_title.lower().strip() == event_lower
            ]
    
    async def save(self) -> None:
        """Save history to disk."""
        await self._ensure_loaded()
        
        # Group records by date for efficient storage
        by_date: dict[str, list[AlertRecord]] = {}
        
        async with self._lock:
            for record in self._records:
                date_str = record.sent_at.strftime("%Y-%m-%d")
                if date_str not in by_date:
                    by_date[date_str] = []
                by_date[date_str].append(record)
        
        # Save each day's records
        for date_str, records in by_date.items():
            filepath = self.history_dir / f"alerts_{date_str}.json"
            
            data = {
                "date": date_str,
                "count": len(records),
                "records": [r.to_dict() for r in records],
            }
            
            # Use a temp file for atomic write
            temp_path = filepath.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(filepath)
        
        # Clean up old files
        await self._cleanup_old_files()
    
    async def load(self) -> None:
        """Load history from disk."""
        self._records = []
        
        if not self.history_dir.exists():
            return
        
        # Find all history files
        files = list(self.history_dir.glob("alerts_*.json"))
        files.sort()
        
        # Load records from each file
        for filepath in files:
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                for record_data in data.get("records", []):
                    record = AlertRecord.from_dict(record_data)
                    self._records.append(record)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                # Log error but continue loading other files
                print(f"Warning: Failed to load {filepath}: {e}")
                continue
    
    async def _cleanup_old_files(self) -> int:
        """Remove history files older than max_days.
        
        Returns:
            Number of files removed
        """
        cutoff = datetime.utcnow() - timedelta(days=self.max_days)
        removed = 0
        
        for filepath in self.history_dir.glob("alerts_*.json"):
            try:
                # Extract date from filename
                date_str = filepath.stem.replace("alerts_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if file_date < cutoff:
                    filepath.unlink()
                    removed += 1
            except (ValueError, OSError):
                continue
        
        return removed
    
    async def export(
        self,
        filepath: str | Path,
        days: int | None = None,
    ) -> int:
        """Export history to a single file.
        
        Args:
            filepath: Export file path
            days: Limit to recent days (None = all)
            
        Returns:
            Number of records exported
        """
        await self._ensure_loaded()
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            records = [r for r in self._records if r.sent_at >= cutoff]
        else:
            records = self._records.copy()
        
        data = {
            "exported_at": datetime.utcnow().isoformat(),
            "count": len(records),
            "records": [r.to_dict() for r in records],
        }
        
        filepath = Path(filepath)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        return len(records)
    
    async def clear(self) -> int:
        """Clear all history.
        
        Returns:
            Number of records cleared
        """
        await self._ensure_loaded()
        
        async with self._lock:
            count = len(self._records)
            self._records.clear()
        
        # Remove all history files
        for filepath in self.history_dir.glob("alerts_*.json"):
            filepath.unlink()
        
        return count


# Convenience functions for simple use cases

async def record_alert_sent(
    alert_id: str,
    event_title: str,
    message: str,
    profit_pct: float,
    **kwargs: Any,
) -> AlertRecord:
    """Quick helper to record an alert.
    
    Uses default history directory.
    """
    history = AlertHistory()
    return await history.record(
        alert_id=alert_id,
        event_title=event_title,
        message=message,
        profit_pct=profit_pct,
        **kwargs,
    )


async def get_alert_stats(days: int = 7) -> dict[str, Any]:
    """Quick helper to get alert stats."""
    history = AlertHistory()
    return await history.get_stats(days=days)
