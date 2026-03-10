"""Price Freshness - Calculate price freshness and apply stale price penalties."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class FreshnessResult:
    """Result of price freshness check."""
    
    freshness_seconds: int
    """Age of price data in seconds."""
    
    is_fresh: bool
    """True if price is considered fresh."""
    
    is_acceptable: bool
    """True if price is acceptable (not rejected)."""
    
    penalty_pct: float
    """Penalty to apply to edge (0 = no penalty)."""
    
    rejection_reason: Optional[str]
    """Reason for rejection if price is rejected."""
    
    warning: Optional[str]
    """Warning message if price is stale but not rejected."""


class PriceFreshness:
    """
    Price freshness calculator with conservative stale price handling.
    
    Conservative thresholds:
    - 0-30s: Fresh, no penalty
    - 30-60s: Stale, 50% edge penalty
    - 60-120s: Very stale, 80% edge penalty
    - >120s: Reject
    """
    
    # Thresholds in seconds
    FRESH_THRESHOLD: int = 30
    STALE_THRESHOLD: int = 60
    VERY_STALE_THRESHOLD: int = 120
    REJECT_THRESHOLD: int = 120
    
    # Penalties
    FRESH_PENALTY: float = 0.0
    STALE_PENALTY: float = 0.50  # 50% reduction
    VERY_STALE_PENALTY: float = 0.80  # 80% reduction
    
    def __init__(
        self,
        fresh_threshold: int = FRESH_THRESHOLD,
        stale_threshold: int = STALE_THRESHOLD,
        reject_threshold: int = REJECT_THRESHOLD,
    ) -> None:
        """
        Initialize price freshness calculator.
        
        Args:
            fresh_threshold: Threshold for "fresh" prices
            stale_threshold: Threshold for "stale" prices
            reject_threshold: Threshold for rejecting prices
        """
        self.fresh_threshold = fresh_threshold
        self.stale_threshold = stale_threshold
        self.reject_threshold = reject_threshold
    
    def calculate_freshness(
        self,
        timestamp: datetime,
        reference_time: Optional[datetime] = None,
    ) -> FreshnessResult:
        """
        Calculate freshness of a price.
        
        Args:
            timestamp: When the price was recorded
            reference_time: Time to compare against (default: now UTC)
            
        Returns:
            FreshnessResult with status and penalties
        """
        reference_time = reference_time or datetime.now(timezone.utc)
        
        # Ensure both timestamps are timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        
        age_seconds = int((reference_time - timestamp).total_seconds())
        
        if age_seconds < 0:
            # Future timestamp - clock skew
            return FreshnessResult(
                freshness_seconds=0,
                is_fresh=True,
                is_acceptable=True,
                penalty_pct=0.0,
                rejection_reason=None,
                warning="Future timestamp detected - possible clock skew",
            )
        
        if age_seconds > self.reject_threshold:
            return FreshnessResult(
                freshness_seconds=age_seconds,
                is_fresh=False,
                is_acceptable=False,
                penalty_pct=1.0,  # 100% penalty = reject
                rejection_reason=f"Price too old: {age_seconds}s (max: {self.reject_threshold}s)",
                warning=None,
            )
        
        if age_seconds > self.stale_threshold:
            return FreshnessResult(
                freshness_seconds=age_seconds,
                is_fresh=False,
                is_acceptable=True,
                penalty_pct=self.VERY_STALE_PENALTY,
                rejection_reason=None,
                warning=f"Very stale price: {age_seconds}s old, 80% edge penalty applied",
            )
        
        if age_seconds > self.fresh_threshold:
            return FreshnessResult(
                freshness_seconds=age_seconds,
                is_fresh=False,
                is_acceptable=True,
                penalty_pct=self.STALE_PENALTY,
                rejection_reason=None,
                warning=f"Stale price: {age_seconds}s old, 50% edge penalty applied",
            )
        
        return FreshnessResult(
            freshness_seconds=age_seconds,
            is_fresh=True,
            is_acceptable=True,
            penalty_pct=self.FRESH_PENALTY,
            rejection_reason=None,
            warning=None,
        )
    
    def calculate_two_leg_freshness(
        self,
        left_timestamp: datetime,
        right_timestamp: datetime,
        reference_time: Optional[datetime] = None,
    ) -> FreshnessResult:
        """
        Calculate combined freshness for both legs of arbitrage.
        
        Uses the older (worse) of the two timestamps.
        
        Args:
            left_timestamp: Left leg price timestamp
            right_timestamp: Right leg price timestamp
            reference_time: Time to compare against
            
        Returns:
            Combined freshness result (conservative: uses oldest)
        """
        reference_time = reference_time or datetime.now(timezone.utc)
        
        left_result = self.calculate_freshness(left_timestamp, reference_time)
        right_result = self.calculate_freshness(right_timestamp, reference_time)
        
        # Use the worse (older) of the two
        if left_result.freshness_seconds >= right_result.freshness_seconds:
            return FreshnessResult(
                freshness_seconds=left_result.freshness_seconds,
                is_fresh=left_result.is_fresh and right_result.is_fresh,
                is_acceptable=left_result.is_acceptable and right_result.is_acceptable,
                penalty_pct=max(left_result.penalty_pct, right_result.penalty_pct),
                rejection_reason=left_result.rejection_reason or right_result.rejection_reason,
                warning=left_result.warning or right_result.warning,
            )
        else:
            return FreshnessResult(
                freshness_seconds=right_result.freshness_seconds,
                is_fresh=left_result.is_fresh and right_result.is_fresh,
                is_acceptable=left_result.is_acceptable and right_result.is_acceptable,
                penalty_pct=max(left_result.penalty_pct, right_result.penalty_pct),
                rejection_reason=left_result.rejection_reason or right_result.rejection_reason,
                warning=left_result.warning or right_result.warning,
            )
    
    def apply_freshness_penalty(
        self,
        edge_pct: float,
        freshness_result: FreshnessResult,
    ) -> float:
        """
        Apply freshness penalty to edge.
        
        Args:
            edge_pct: Original edge percentage
            freshness_result: Freshness check result
            
        Returns:
            Penalized edge percentage
        """
        if not freshness_result.is_acceptable:
            return 0.0  # Rejected
        
        return edge_pct * (1.0 - freshness_result.penalty_pct)
    
    def is_price_acceptable(self, timestamp: datetime) -> bool:
        """Quick check if price is acceptable (not rejected)."""
        result = self.calculate_freshness(timestamp)
        return result.is_acceptable
    
    def get_freshness_tier(self, freshness_seconds: int) -> str:
        """Get freshness tier as string."""
        if freshness_seconds <= self.fresh_threshold:
            return "fresh"
        elif freshness_seconds <= self.stale_threshold:
            return "stale"
        elif freshness_seconds <= self.reject_threshold:
            return "very_stale"
        else:
            return "rejected"
