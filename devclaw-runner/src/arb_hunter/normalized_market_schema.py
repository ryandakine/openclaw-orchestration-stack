"""Pydantic schema for normalized market data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MarketType(str, Enum):
    """Types of prediction markets."""

    BINARY = "binary"
    MULTIPLE_CHOICE = "multiple_choice"
    SCALAR = "scalar"
    CATEGORICAL = "categorical"


class Category(str, Enum):
    """Market categories."""

    POLITICS = "politics"
    SPORTS = "sports"
    CRYPTO = "crypto"
    ECONOMICS = "economics"
    ENTERTAINMENT = "entertainment"
    TECHNOLOGY = "technology"
    SCIENCE = "science"
    OTHER = "other"


class Outcome(BaseModel):
    """Normalized outcome representation."""

    name: str = Field(description="Outcome name (e.g., 'Yes', 'No', 'Trump', 'Biden')")
    probability: Decimal = Field(
        description="Implied probability (0.0 to 1.0)",
        max_digits=5,
        decimal_places=4,
    )
    price: Decimal | None = Field(
        default=None,
        description="Raw price from source (e.g., $0.65)",
    )
    volume: Decimal | None = Field(
        default=None,
        description="Volume for this outcome",
    )

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, v: Decimal) -> Decimal:
        """Ensure probability is between 0 and 1."""
        if v < 0 or v > 1:
            raise ValueError(f"Probability must be between 0 and 1, got {v}")
        return v

    class Config:
        """Pydantic config."""

        json_encoders = {Decimal: str}


class LiquidityInfo(BaseModel):
    """Normalized liquidity information."""

    total_volume: Decimal | None = Field(
        default=None,
        description="Total trading volume",
    )
    open_interest: Decimal | None = Field(
        default=None,
        description="Open interest if available",
    )
    bid_ask_spread: Decimal | None = Field(
        default=None,
        description="Average bid-ask spread (normalized 0-1)",
    )
    depth_score: Decimal | None = Field(
        default=None,
        description="Liquidity depth score (0-100)",
    )

    class Config:
        """Pydantic config."""

        json_encoders = {Decimal: str}


class NormalizedMarket(BaseModel):
    """Canonical normalized market format.

    This is the standard format that all market data sources
    are transformed into for arbitrage detection.
    """

    # Source identification
    source: str = Field(
        description="Data source (e.g., 'polymarket', 'draftkings', 'fanduel')"
    )
    source_event_id: str = Field(
        description="Original event ID from the source"
    )
    source_market_id: str | None = Field(
        default=None,
        description="Original market ID from the source (if different from event)"
    )

    # Market metadata
    title: str = Field(
        description="Human-readable market title/question"
    )
    description: str | None = Field(
        default=None,
        description="Additional market description"
    )
    market_type: MarketType = Field(
        description="Type of prediction market"
    )
    category: Category = Field(
        description="Market category"
    )

    # Timing
    start_time: datetime | None = Field(
        default=None,
        description="When the event starts (for sports)"
    )
    resolution_time: datetime | None = Field(
        default=None,
        description="When the market resolves"
    )

    # Outcomes
    outcomes: list[Outcome] = Field(
        description="List of possible outcomes with probabilities"
    )

    # Liquidity
    liquidity: LiquidityInfo = Field(
        default_factory=LiquidityInfo,
        description="Normalized liquidity information"
    )

    # Links
    url: str | None = Field(
        default=None,
        description="Direct URL to the market"
    )
    image_url: str | None = Field(
        default=None,
        description="Market image/icon URL"
    )

    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="Additional tags for categorization"
    )
    raw_source_data: dict[str, Any] | None = Field(
        default=None,
        description="Original raw data (for debugging/audit)",
        exclude=True,  # Don't include in serialization by default
    )

    # Timestamps
    last_updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this record was last updated"
    )
    source_timestamp: datetime | None = Field(
        default=None,
        description="Timestamp from the source API"
    )

    @property
    def start_or_resolution_time(self) -> datetime | None:
        """Get either start time or resolution time (for convenience)."""
        return self.start_time or self.resolution_time

    @property
    def best_bid(self) -> Decimal | None:
        """Get the best available bid (highest probability)."""
        if not self.outcomes:
            return None
        return max(o.probability for o in self.outcomes)

    @property
    def best_ask(self) -> Decimal | None:
        """Get the best available ask (lowest probability)."""
        if not self.outcomes:
            return None
        return min(o.probability for o in self.outcomes)

    def get_outcome(self, name: str) -> Outcome | None:
        """Get an outcome by name (case-insensitive)."""
        name_lower = name.lower()
        for outcome in self.outcomes:
            if outcome.name.lower() == name_lower:
                return outcome
        return None

    class Config:
        """Pydantic config."""

        json_encoders = {Decimal: str, datetime: lambda v: v.isoformat()}
        frozen = False
