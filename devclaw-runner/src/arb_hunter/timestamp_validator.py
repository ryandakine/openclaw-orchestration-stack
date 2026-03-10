"""Timestamp validation for market data freshness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .market_normalization_error import MarketNormalizationError
from .normalized_market_schema import NormalizedMarket


class FreshnessStatus(Enum):
    """Data freshness status."""

    FRESH = "fresh"  # Data is recent
    STALE = "stale"  # Data is older than threshold
    EXPIRED = "expired"  # Data is very old
    UNKNOWN = "unknown"  # Cannot determine freshness


@dataclass
class ValidationResult:
    """Result of timestamp validation."""

    status: FreshnessStatus
    age_seconds: float | None
    threshold_seconds: float
    message: str
    market_id: str


class TimestampValidator:
    """Validates market data freshness.

    Rejects stale data (>120s by default) and tracks
    data age for quality scoring.
    """

    # Default freshness thresholds
    DEFAULT_THRESHOLD = 120.0  # 2 minutes
    EXPIRED_THRESHOLD = 300.0  # 5 minutes

    def __init__(
        self,
        threshold_seconds: float = DEFAULT_THRESHOLD,
        expired_threshold: float = EXPIRED_THRESHOLD,
        reject_stale: bool = True,
    ) -> None:
        """Initialize the validator.

        Args:
            threshold_seconds: Staleness threshold
            expired_threshold: Expired threshold
            reject_stale: Whether to reject stale data
        """
        self.threshold_seconds = threshold_seconds
        self.expired_threshold = expired_threshold
        self.reject_stale = reject_stale
        self.validation_history: list[ValidationResult] = []
        self.rejected_count = 0
        self.accepted_count = 0

    def _now_utc(self) -> datetime:
        """Get current UTC time.

        Returns:
            Current datetime in UTC
        """
        return datetime.now(timezone.utc)

    def _calculate_age(self, timestamp: datetime | None) -> float | None:
        """Calculate age of data in seconds.

        Args:
            timestamp: Data timestamp

        Returns:
            Age in seconds or None if timestamp is None
        """
        if timestamp is None:
            return None

        now = self._now_utc()

        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        diff = (now - timestamp).total_seconds()
        return max(0.0, diff)  # Handle future timestamps

    def validate(
        self,
        market: NormalizedMarket,
    ) -> ValidationResult:
        """Validate a single market's freshness.

        Args:
            market: Market to validate

        Returns:
            Validation result
        """
        market_id = f"{market.source}:{market.source_event_id}"

        # Try to get the most relevant timestamp
        timestamp = (
            market.source_timestamp
            or market.last_updated_at
        )

        age = self._calculate_age(timestamp)

        if age is None:
            result = ValidationResult(
                status=FreshnessStatus.UNKNOWN,
                age_seconds=None,
                threshold_seconds=self.threshold_seconds,
                message=f"No timestamp available for {market_id}",
                market_id=market_id,
            )
        elif age > self.expired_threshold:
            result = ValidationResult(
                status=FreshnessStatus.EXPIRED,
                age_seconds=age,
                threshold_seconds=self.threshold_seconds,
                message=f"Data expired: {age:.1f}s old (threshold: {self.expired_threshold}s)",
                market_id=market_id,
            )
        elif age > self.threshold_seconds:
            result = ValidationResult(
                status=FreshnessStatus.STALE,
                age_seconds=age,
                threshold_seconds=self.threshold_seconds,
                message=f"Data stale: {age:.1f}s old (threshold: {self.threshold_seconds}s)",
                market_id=market_id,
            )
        else:
            result = ValidationResult(
                status=FreshnessStatus.FRESH,
                age_seconds=age,
                threshold_seconds=self.threshold_seconds,
                message=f"Data fresh: {age:.1f}s old",
                market_id=market_id,
            )

        self.validation_history.append(result)

        if result.status in (FreshnessStatus.STALE, FreshnessStatus.EXPIRED):
            self.rejected_count += 1
        else:
            self.accepted_count += 1

        return result

    def is_acceptable(self, market: NormalizedMarket) -> bool:
        """Check if market data is acceptable (not rejected).

        Args:
            market: Market to check

        Returns:
            True if acceptable
        """
        if not self.reject_stale:
            return True

        result = self.validate(market)
        return result.status != FreshnessStatus.STALE and result.status != FreshnessStatus.EXPIRED

    def filter_markets(
        self,
        markets: list[NormalizedMarket],
    ) -> tuple[list[NormalizedMarket], list[ValidationResult]]:
        """Filter markets by freshness.

        Args:
            markets: List of markets to filter

        Returns:
            Tuple of (accepted markets, rejected results)
        """
        accepted: list[NormalizedMarket] = []
        rejected: list[ValidationResult] = []

        for market in markets:
            result = self.validate(market)

            if self.reject_stale and result.status in (
                FreshnessStatus.STALE,
                FreshnessStatus.EXPIRED,
            ):
                rejected.append(result)
            else:
                accepted.append(market)

        return accepted, rejected

    def validate_or_raise(self, market: NormalizedMarket) -> NormalizedMarket:
        """Validate market or raise exception if stale.

        Args:
            market: Market to validate

        Returns:
            The market if valid

        Raises:
            MarketNormalizationError: If data is stale and reject_stale is True
        """
        result = self.validate(market)

        if self.reject_stale and result.status == FreshnessStatus.STALE:
            raise MarketNormalizationError(
                f"Stale data rejected: {result.message}",
                source=market.source,
            )
        elif result.status == FreshnessStatus.EXPIRED:
            raise MarketNormalizationError(
                f"Expired data rejected: {result.message}",
                source=market.source,
            )

        return market

    def get_stats(self) -> dict[str, int | float]:
        """Get validation statistics.

        Returns:
            Statistics dict
        """
        total = self.accepted_count + self.rejected_count
        acceptance_rate = (
            (self.accepted_count / total * 100) if total > 0 else 100.0
        )

        return {
            "total_validated": total,
            "accepted": self.accepted_count,
            "rejected": self.rejected_count,
            "acceptance_rate": acceptance_rate,
        }

    def get_average_age(self) -> float | None:
        """Get average age of validated data.

        Returns:
            Average age in seconds or None
        """
        ages = [
            r.age_seconds
            for r in self.validation_history
            if r.age_seconds is not None
        ]
        if not ages:
            return None
        return sum(ages) / len(ages)

    def reset_stats(self) -> None:
        """Reset validation statistics."""
        self.validation_history.clear()
        self.rejected_count = 0
        self.accepted_count = 0

    def create_freshness_metadata(self, market: NormalizedMarket) -> dict[str, Any]:
        """Create freshness metadata for a market.

        Args:
            market: Market to check

        Returns:
            Metadata dict
        """
        result = self.validate(market)

        return {
            "status": result.status.value,
            "age_seconds": result.age_seconds,
            "threshold_seconds": result.threshold_seconds,
            "validated_at": self._now_utc().isoformat(),
        }


class FreshnessAwareMarket(NormalizedMarket):
    """Extended market with freshness metadata."""

    freshness_metadata: dict[str, Any]


async def validate_markets_freshness(
    markets: list[NormalizedMarket],
    threshold_seconds: float = 120.0,
    reject_stale: bool = True,
) -> tuple[list[NormalizedMarket], list[ValidationResult]]:
    """Validate freshness of multiple markets.

    Args:
        markets: Markets to validate
        threshold_seconds: Staleness threshold
        reject_stale: Whether to reject stale data

    Returns:
        Tuple of (accepted markets, rejected results)
    """
    validator = TimestampValidator(
        threshold_seconds=threshold_seconds,
        reject_stale=reject_stale,
    )
    return validator.filter_markets(markets)
