"""
market_logger.py - Log markets fetched per source with counts, samples, and errors.

Tracks market data retrieval from various bookmaker APIs including success rates,
response times, and encountered errors.
"""

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

import structlog

from .logger_config import get_logger


class FetchStatus(str, Enum):
    """Status of a market fetch operation."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CACHE_HIT = "cache_hit"


@dataclass
class MarketFetchRecord:
    """Record of a market fetch operation from a single source."""
    fetch_id: str
    run_id: str
    source: str  # Bookmaker name
    sport: Optional[str] = None
    league: Optional[str] = None
    fetch_status: FetchStatus = FetchStatus.SUCCESS
    markets_count: int = 0
    events_count: int = 0
    sample_market_ids: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    response_time_ms: Optional[float] = None
    cache_hit: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["fetch_status"] = self.fetch_status.value
        return result


class MarketLogger:
    """
    Logger for market fetching operations.
    
    Tracks market data retrieval from bookmaker APIs with detailed metrics
    including counts, samples, response times, and errors.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("market_logger")
        self.log_dir = Path(log_dir) if log_dir else None
        self._fetch_records: List[MarketFetchRecord] = []
        self._source_stats: Dict[str, Dict[str, Any]] = {}
    
    def log_fetch_start(
        self,
        run_id: str,
        source: str,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log the start of a market fetch operation.
        
        Args:
            run_id: Parent run ID
            source: Bookmaker/source name
            sport: Sport being fetched
            league: League being fetched
            metadata: Additional metadata
            
        Returns:
            fetch_id for tracking this operation
        """
        fetch_id = str(uuid.uuid4())
        
        self.logger.debug(
            "market_fetch_started",
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            league=league,
            metadata=metadata
        )
        
        return fetch_id
    
    def log_fetch_complete(
        self,
        fetch_id: str,
        run_id: str,
        source: str,
        markets_count: int,
        events_count: int,
        market_ids: List[str],
        response_time_ms: float,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        status: FetchStatus = FetchStatus.SUCCESS,
        cache_hit: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MarketFetchRecord:
        """
        Log successful completion of a market fetch.
        
        Args:
            fetch_id: Fetch operation ID
            run_id: Parent run ID
            source: Bookmaker/source name
            markets_count: Number of markets fetched
            events_count: Number of events fetched
            market_ids: List of market IDs (sample stored)
            response_time_ms: API response time in milliseconds
            sport: Sport fetched
            league: League fetched
            status: Fetch status
            cache_hit: Whether result came from cache
            metadata: Additional metadata
            
        Returns:
            The MarketFetchRecord
        """
        # Store only a sample of market IDs (first 10 and last 5)
        sample_ids = self._sample_market_ids(market_ids)
        
        record = MarketFetchRecord(
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            league=league,
            fetch_status=status,
            markets_count=markets_count,
            events_count=events_count,
            sample_market_ids=sample_ids,
            response_time_ms=response_time_ms,
            cache_hit=cache_hit,
            metadata=metadata or {}
        )
        
        self._fetch_records.append(record)
        self._update_source_stats(source, record)
        
        log_level = "info" if status == FetchStatus.SUCCESS else "warning"
        log_method = getattr(self.logger, log_level)
        
        log_method(
            "market_fetch_completed",
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            league=league,
            status=status.value,
            markets_count=markets_count,
            events_count=events_count,
            sample_market_ids=sample_ids,
            response_time_ms=round(response_time_ms, 2),
            cache_hit=cache_hit
        )
        
        return record
    
    def log_fetch_error(
        self,
        fetch_id: str,
        run_id: str,
        source: str,
        error_type: str,
        error_message: str,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        response_time_ms: Optional[float] = None,
        retry_count: int = 0,
        http_status: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MarketFetchRecord:
        """
        Log a failed market fetch operation.
        
        Args:
            fetch_id: Fetch operation ID
            run_id: Parent run ID
            source: Bookmaker/source name
            error_type: Type of error (API, Parse, Timeout, etc.)
            error_message: Error description
            sport: Sport being fetched
            league: League being fetched
            response_time_ms: Response time before failure
            retry_count: Number of retries attempted
            http_status: HTTP status code if applicable
            metadata: Additional metadata
            
        Returns:
            The MarketFetchRecord with error details
        """
        error_details = {
            "error_type": error_type,
            "error_message": error_message,
            "retry_count": retry_count
        }
        if http_status:
            error_details["http_status"] = http_status
        
        record = MarketFetchRecord(
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            league=league,
            fetch_status=FetchStatus.FAILED,
            markets_count=0,
            events_count=0,
            errors=[error_details],
            response_time_ms=response_time_ms,
            metadata=metadata or {}
        )
        
        self._fetch_records.append(record)
        self._update_source_stats(source, record, error=True)
        
        self.logger.error(
            "market_fetch_failed",
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            league=league,
            error_type=error_type,
            error_message=error_message,
            response_time_ms=round(response_time_ms, 2) if response_time_ms else None,
            retry_count=retry_count,
            http_status=http_status
        )
        
        return record
    
    def log_rate_limited(
        self,
        fetch_id: str,
        run_id: str,
        source: str,
        retry_after: Optional[int] = None,
        sport: Optional[str] = None
    ) -> None:
        """Log a rate limit event."""
        self.logger.warning(
            "market_fetch_rate_limited",
            fetch_id=fetch_id,
            run_id=run_id,
            source=source,
            sport=sport,
            retry_after_seconds=retry_after
        )
    
    def get_fetch_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of market fetches.
        
        Args:
            run_id: Filter by run ID (optional)
            
        Returns:
            Summary dictionary with counts and statistics
        """
        records = self._fetch_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        total_fetches = len(records)
        successful = len([r for r in records if r.fetch_status == FetchStatus.SUCCESS])
        failed = len([r for r in records if r.fetch_status == FetchStatus.FAILED])
        cache_hits = len([r for r in records if r.cache_hit])
        
        total_markets = sum(r.markets_count for r in records)
        avg_response_time = (
            sum(r.response_time_ms or 0 for r in records) / total_fetches
            if total_fetches > 0 else 0
        )
        
        # Group by source
        by_source: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if record.source not in by_source:
                by_source[record.source] = {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "markets_count": 0,
                    "avg_response_time_ms": 0
                }
            by_source[record.source]["total"] += 1
            by_source[record.source]["markets_count"] += record.markets_count
            if record.fetch_status == FetchStatus.SUCCESS:
                by_source[record.source]["successful"] += 1
            elif record.fetch_status == FetchStatus.FAILED:
                by_source[record.source]["failed"] += 1
        
        return {
            "total_fetches": total_fetches,
            "successful": successful,
            "failed": failed,
            "cache_hits": cache_hits,
            "total_markets": total_markets,
            "avg_response_time_ms": round(avg_response_time, 2),
            "by_source": by_source
        }
    
    def get_source_errors(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get error records, optionally filtered by source."""
        errors = []
        for record in self._fetch_records:
            if record.errors:
                if source is None or record.source == source:
                    errors.append({
                        "fetch_id": record.fetch_id,
                        "run_id": record.run_id,
                        "source": record.source,
                        "timestamp": record.timestamp.isoformat(),
                        "errors": record.errors
                    })
        return errors
    
    def persist_records(self, run_id: str) -> Optional[Path]:
        """
        Persist fetch records for a run to disk.
        
        Args:
            run_id: Run ID to persist records for
            
        Returns:
            Path to the persisted file or None
        """
        if not self.log_dir:
            return None
        
        records = [r for r in self._fetch_records if r.run_id == run_id]
        if not records:
            return None
        
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            run_dir = self.log_dir / "markets" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{run_id}_markets.json"
            with open(file_path, "w") as f:
                json.dump([r.to_dict() for r in records], f, indent=2)
            
            return file_path
        except Exception as e:
            self.logger.error(
                "failed_to_persist_market_records",
                run_id=run_id,
                error=str(e)
            )
            return None
    
    def _sample_market_ids(self, market_ids: List[str], max_samples: int = 15) -> List[str]:
        """Create a sample of market IDs (first 10 + last 5)."""
        if len(market_ids) <= max_samples:
            return market_ids
        
        first_n = max_samples // 3 * 2  # 2/3 from start
        last_n = max_samples - first_n  # 1/3 from end
        
        return market_ids[:first_n] + market_ids[-last_n:]
    
    def _update_source_stats(
        self,
        source: str,
        record: MarketFetchRecord,
        error: bool = False
    ) -> None:
        """Update running statistics for a source."""
        if source not in self._source_stats:
            self._source_stats[source] = {
                "total_fetches": 0,
                "successful": 0,
                "failed": 0,
                "total_markets": 0,
                "total_response_time_ms": 0
            }
        
        stats = self._source_stats[source]
        stats["total_fetches"] += 1
        stats["total_markets"] += record.markets_count
        
        if record.response_time_ms:
            stats["total_response_time_ms"] += record.response_time_ms
        
        if error or record.fetch_status == FetchStatus.FAILED:
            stats["failed"] += 1
        else:
            stats["successful"] += 1
    
    def clear_records(self, run_id: Optional[str] = None) -> None:
        """Clear stored records, optionally filtered by run_id."""
        if run_id:
            self._fetch_records = [r for r in self._fetch_records if r.run_id != run_id]
        else:
            self._fetch_records.clear()


# Singleton instance
_market_logger_instance: Optional[MarketLogger] = None


def initialize_market_logger(log_dir: Optional[Path] = None) -> MarketLogger:
    """Initialize the global market logger instance."""
    global _market_logger_instance
    _market_logger_instance = MarketLogger(log_dir=log_dir)
    return _market_logger_instance


def get_market_logger() -> MarketLogger:
    """Get the global market logger instance."""
    if _market_logger_instance is None:
        return MarketLogger()
    return _market_logger_instance
