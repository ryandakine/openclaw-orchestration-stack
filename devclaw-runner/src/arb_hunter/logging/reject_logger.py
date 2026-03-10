"""
reject_logger.py - Log rejected arbitrage opportunities with detailed reasons.

Tracks why arbitrage opportunities were rejected including low edge, stale data,
low confidence matches, and other filtering criteria.
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

import structlog

from .logger_config import get_logger


class RejectReason(str, Enum):
    """Reasons for rejecting an arbitrage opportunity."""
    LOW_EDGE = "low_edge"  # Edge below threshold
    STALE_DATA = "stale_data"  # Data too old
    LOW_CONFIDENCE = "low_confidence"  # Match confidence too low
    PRICE_MISMATCH = "price_mismatch"  # Prices don't match expected
    SUSPICIOUS_ODDS = "suspicious_odds"  # Odds seem unrealistic
    MARKET_CLOSING = "market_closing"  # Market closing soon
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"  # Not enough volume
    SOURCE_EXCLUDED = "source_excluded"  # Source in exclusion list
    DUPLICATE = "duplicate"  # Already identified
    BLACKLISTED_EVENT = "blacklisted_event"  # Event is blacklisted
    CALCULATION_ERROR = "calculation_error"  # Error in calculation
    MAX_EXPOSURE = "max_exposure"  # Would exceed exposure limits
    ODDS_CHANGED = "odds_changed"  # Odds changed during processing


@dataclass
class RejectedOpportunity:
    """Record of a rejected arbitrage opportunity."""
    reject_id: str
    run_id: str
    arb_id: Optional[str]  # Original arb ID if assigned
    reject_reason: RejectReason
    source_a: str
    market_id_a: str
    source_b: str
    market_id_b: str
    # Calculated values at time of rejection
    edge_percent: Optional[float] = None
    profit_percent: Optional[float] = None
    stake_a: Optional[float] = None
    stake_b: Optional[float] = None
    # Thresholds that were applied
    edge_threshold: Optional[float] = None
    confidence_threshold: Optional[float] = None
    max_age_seconds: Optional[int] = None
    # Context
    match_score: Optional[float] = None
    data_age_seconds: Optional[float] = None
    odds_a: Optional[Dict[str, Any]] = None
    odds_b: Optional[Dict[str, Any]] = None
    # Rejection details
    rejection_message: Optional[str] = None
    rejection_details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["reject_reason"] = self.reject_reason.value
        return result


@dataclass
class RejectionSummary:
    """Summary of rejections for a run."""
    run_id: str
    total_rejected: int = 0
    by_reason: Dict[str, int] = field(default_factory=dict)
    total_potential_profit: float = 0.0
    highest_rejected_edge: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


class RejectLogger:
    """
    Logger for rejected arbitrage opportunities.
    
    Tracks opportunities that were identified but rejected, with detailed
    reasons and context to help tune filtering criteria.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("reject_logger")
        self.log_dir = Path(log_dir) if log_dir else None
        self._rejected_records: List[RejectedOpportunity] = []
        self._thresholds: Dict[str, Any] = {}
    
    def log_rejection(
        self,
        reject_id: str,
        run_id: str,
        reject_reason: RejectReason,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        arb_id: Optional[str] = None,
        edge_percent: Optional[float] = None,
        profit_percent: Optional[float] = None,
        stake_a: Optional[float] = None,
        stake_b: Optional[float] = None,
        edge_threshold: Optional[float] = None,
        confidence_threshold: Optional[float] = None,
        max_age_seconds: Optional[int] = None,
        match_score: Optional[float] = None,
        data_age_seconds: Optional[float] = None,
        odds_a: Optional[Dict[str, Any]] = None,
        odds_b: Optional[Dict[str, Any]] = None,
        rejection_message: Optional[str] = None,
        rejection_details: Optional[Dict[str, Any]] = None
    ) -> RejectedOpportunity:
        """
        Log a rejected arbitrage opportunity.
        
        Args:
            reject_id: Unique rejection identifier
            run_id: Parent run ID
            reject_reason: Primary reason for rejection
            source_a: First bookmaker source
            market_id_a: Market ID from source A
            source_b: Second bookmaker source
            market_id_b: Market ID from source B
            arb_id: Original arb opportunity ID if assigned
            edge_percent: Calculated edge percentage
            profit_percent: Calculated profit percentage
            stake_a: Recommended stake for source A
            stake_b: Recommended stake for source B
            edge_threshold: Edge threshold that was applied
            confidence_threshold: Confidence threshold applied
            max_age_seconds: Maximum data age allowed
            match_score: Market match confidence score
            data_age_seconds: Age of data in seconds
            odds_a: Odds from source A
            odds_b: Odds from source B
            rejection_message: Human-readable rejection message
            rejection_details: Additional rejection context
            
        Returns:
            The RejectedOpportunity record
        """
        record = RejectedOpportunity(
            reject_id=reject_id,
            run_id=run_id,
            arb_id=arb_id,
            reject_reason=reject_reason,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            edge_percent=edge_percent,
            profit_percent=profit_percent,
            stake_a=stake_a,
            stake_b=stake_b,
            edge_threshold=edge_threshold,
            confidence_threshold=confidence_threshold,
            max_age_seconds=max_age_seconds,
            match_score=match_score,
            data_age_seconds=data_age_seconds,
            odds_a=odds_a,
            odds_b=odds_b,
            rejection_message=rejection_message,
            rejection_details=rejection_details or {}
        )
        
        self._rejected_records.append(record)
        
        # Build structured log data
        log_data = {
            "reject_id": reject_id,
            "run_id": run_id,
            "arb_id": arb_id,
            "reject_reason": reject_reason.value,
            "source_pair": f"{source_a}:{source_b}",
            "edge_percent": round(edge_percent, 4) if edge_percent else None,
            "profit_percent": round(profit_percent, 4) if profit_percent else None,
            "match_score": round(match_score, 4) if match_score else None,
            "data_age_seconds": round(data_age_seconds, 2) if data_age_seconds else None,
        }
        
        if rejection_message:
            log_data["message"] = rejection_message
        
        # Log based on how close the opportunity was
        if edge_percent and edge_threshold and edge_percent >= edge_threshold * 0.8:
            # Within 80% of threshold - nearly made it
            self.logger.warning("opportunity_rejected_near_threshold", **log_data)
        else:
            self.logger.info("opportunity_rejected", **log_data)
        
        return record
    
    def log_low_edge_rejection(
        self,
        reject_id: str,
        run_id: str,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        edge_percent: float,
        edge_threshold: float,
        **kwargs
    ) -> RejectedOpportunity:
        """
        Convenience method for logging low edge rejections.
        
        Args:
            reject_id: Unique rejection identifier
            run_id: Parent run ID
            source_a: First bookmaker source
            market_id_a: Market ID from source A
            source_b: Second bookmaker source
            market_id_b: Market ID from source B
            edge_percent: Calculated edge percentage
            edge_threshold: Minimum required edge
            **kwargs: Additional rejection details
            
        Returns:
            The RejectedOpportunity record
        """
        gap = edge_threshold - edge_percent
        rejection_message = (
            f"Edge {edge_percent:.3f}% below threshold {edge_threshold:.3f}% "
            f"(gap: {gap:.3f}%)"
        )
        
        return self.log_rejection(
            reject_id=reject_id,
            run_id=run_id,
            reject_reason=RejectReason.LOW_EDGE,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            edge_percent=edge_percent,
            edge_threshold=edge_threshold,
            rejection_message=rejection_message,
            rejection_details={
                "edge_gap": gap,
                "edge_gap_percent": round((gap / edge_threshold) * 100, 2) if edge_threshold else None
            },
            **kwargs
        )
    
    def log_stale_data_rejection(
        self,
        reject_id: str,
        run_id: str,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        data_age_seconds: float,
        max_age_seconds: int,
        **kwargs
    ) -> RejectedOpportunity:
        """Convenience method for logging stale data rejections."""
        overage = data_age_seconds - max_age_seconds
        rejection_message = (
            f"Data age {data_age_seconds:.1f}s exceeds maximum {max_age_seconds}s "
            f"(overage: {overage:.1f}s)"
        )
        
        return self.log_rejection(
            reject_id=reject_id,
            run_id=run_id,
            reject_reason=RejectReason.STALE_DATA,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            data_age_seconds=data_age_seconds,
            max_age_seconds=max_age_seconds,
            rejection_message=rejection_message,
            rejection_details={
                "overage_seconds": overage,
                "data_freshness_ratio": round(max_age_seconds / data_age_seconds, 4) if data_age_seconds else 0
            },
            **kwargs
        )
    
    def log_low_confidence_rejection(
        self,
        reject_id: str,
        run_id: str,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        match_score: float,
        confidence_threshold: float,
        **kwargs
    ) -> RejectedOpportunity:
        """Convenience method for logging low confidence rejections."""
        gap = confidence_threshold - match_score
        rejection_message = (
            f"Match score {match_score:.3f} below threshold {confidence_threshold:.3f} "
            f"(gap: {gap:.3f})"
        )
        
        return self.log_rejection(
            reject_id=reject_id,
            run_id=run_id,
            reject_reason=RejectReason.LOW_CONFIDENCE,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            match_score=match_score,
            confidence_threshold=confidence_threshold,
            rejection_message=rejection_message,
            rejection_details={
                "confidence_gap": gap,
                "match_factors": kwargs.get("match_factors", {})
            },
            **kwargs
        )
    
    def set_thresholds(self, thresholds: Dict[str, Any]) -> None:
        """Set the current thresholds being applied."""
        self._thresholds = thresholds
    
    def get_rejection_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary of rejections.
        
        Args:
            run_id: Filter by run ID (optional)
            
        Returns:
            Summary dictionary
        """
        records = self._rejected_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        total = len(records)
        by_reason: Dict[str, int] = {}
        by_source_pair: Dict[str, int] = {}
        
        total_potential_profit = 0.0
        highest_edge = 0.0
        
        for record in records:
            # Count by reason
            reason = record.reject_reason.value
            by_reason[reason] = by_reason.get(reason, 0) + 1
            
            # Count by source pair
            pair = f"{record.source_a}:{record.source_b}"
            by_source_pair[pair] = by_source_pair.get(pair, 0) + 1
            
            # Accumulate potential profit
            if record.profit_percent:
                total_potential_profit += record.profit_percent
            
            # Track highest edge
            if record.edge_percent and record.edge_percent > highest_edge:
                highest_edge = record.edge_percent
        
        return {
            "total_rejected": total,
            "by_reason": by_reason,
            "by_source_pair": by_source_pair,
            "total_potential_profit": round(total_potential_profit, 4),
            "highest_rejected_edge": round(highest_edge, 4),
            "thresholds_applied": self._thresholds
        }
    
    def get_rejections_by_reason(
        self,
        reason: RejectReason,
        run_id: Optional[str] = None
    ) -> List[RejectedOpportunity]:
        """Get rejections filtered by reason."""
        records = self._rejected_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.reject_reason == reason]
    
    def get_near_misses(
        self,
        run_id: Optional[str] = None,
        edge_tolerance: float = 0.5
    ) -> List[RejectedOpportunity]:
        """
        Get opportunities that were close to passing (near misses).
        
        Args:
            run_id: Filter by run ID
            edge_tolerance: Percentage points below threshold to consider "near"
            
        Returns:
            List of near-miss rejections
        """
        records = self._rejected_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        near_misses = []
        for record in records:
            if record.reject_reason == RejectReason.LOW_EDGE:
                if record.edge_percent and record.edge_threshold:
                    gap = record.edge_threshold - record.edge_percent
                    if gap <= edge_tolerance:
                        near_misses.append(record)
        
        return sorted(near_misses, key=lambda x: x.edge_percent or 0, reverse=True)
    
    def persist_records(self, run_id: str) -> Optional[Path]:
        """Persist rejection records for a run to disk."""
        if not self.log_dir:
            return None
        
        records = [r for r in self._rejected_records if r.run_id == run_id]
        if not records:
            return None
        
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            run_dir = self.log_dir / "rejects" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{run_id}_rejects.json"
            with open(file_path, "w") as f:
                json.dump({
                    "run_id": run_id,
                    "rejected_opportunities": [r.to_dict() for r in records],
                    "summary": self.get_rejection_summary(run_id),
                    "thresholds_applied": self._thresholds
                }, f, indent=2)
            
            return file_path
        except Exception as e:
            self.logger.error(
                "failed_to_persist_reject_records",
                run_id=run_id,
                error=str(e)
            )
            return None
    
    def clear_records(self, run_id: Optional[str] = None) -> None:
        """Clear stored records."""
        if run_id:
            self._rejected_records = [r for r in self._rejected_records if r.run_id != run_id]
        else:
            self._rejected_records.clear()


# Singleton instance
_reject_logger_instance: Optional[RejectLogger] = None


def initialize_reject_logger(log_dir: Optional[Path] = None) -> RejectLogger:
    """Initialize the global reject logger instance."""
    global _reject_logger_instance
    _reject_logger_instance = RejectLogger(log_dir=log_dir)
    return _reject_logger_instance


def get_reject_logger() -> RejectLogger:
    """Get the global reject logger instance."""
    if _reject_logger_instance is None:
        return RejectLogger()
    return _reject_logger_instance
