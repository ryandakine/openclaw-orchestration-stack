"""Arbitrage Opportunity Schema - Pydantic dataclass for arb opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ArbOpportunity:
    """
    Conservative arbitrage opportunity schema.
    
    All monetary values in USD, percentages as decimals (e.g., 0.02 = 2%).
    """
    
    # Identity (required)
    arb_id: str
    """Unique identifier for this arb opportunity (hash of legs + timestamp)."""
    
    event_title: str
    """Human-readable event title for display."""
    
    # Arbitrage Legs (required)
    left_leg: dict
    """Left leg details: venue, odds, side, market_id, liquidity."""
    
    right_leg: dict
    """Right leg details: venue, odds, side, market_id, liquidity."""
    
    # Edge Calculations (required)
    gross_edge_pct: float
    """Gross arbitrage edge before any costs (e.g., 0.05 = 5%)."""
    
    fees_pct: float
    """Total fees as percentage of position (e.g., 0.015 = 1.5%)."""
    
    slippage_pct: float
    """Estimated slippage as percentage (e.g., 0.005 = 0.5%)."""
    
    # Quality Scores (required)
    match_score: float
    """Confidence score (0-1) that legs match same event."""
    
    resolution_confidence: float
    """Confidence (0-1) that resolution semantics are identical."""
    
    freshness_seconds: int
    """Age of price data in seconds."""
    
    # Sizing (required)
    max_size: float
    """Maximum position size in USD based on liquidity constraints."""
    
    # Edge - calculated (optional, defaults)
    net_edge_pct: float = field(default=0.0)
    """Net edge after fees and slippage (gross - fees - slippage)."""
    
    expected_profit: float = field(default=0.0)
    """Expected profit in USD at max_size."""
    
    # Alert Status (optional, defaults)
    alertable: bool = field(default=False)
    """Whether this opportunity passes all filters for alerting."""
    
    # Timestamps (optional, defaults)
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    """When this opportunity was discovered."""
    
    expires_at: Optional[datetime] = None
    """When this opportunity expires (event start time)."""
    
    # Validation flags (optional, defaults)
    passed_validation: bool = field(default=False)
    """Whether this opportunity passed all validation checks."""
    
    validation_errors: list[str] = field(default_factory=list)
    """List of validation failure reasons if any."""
    
    def __post_init__(self) -> None:
        """Ensure net_edge is calculated if not provided."""
        if self.net_edge_pct == 0.0 and self.gross_edge_pct > 0:
            self.net_edge_pct = self.gross_edge_pct - self.fees_pct - self.slippage_pct
        
        # Ensure expected_profit is calculated
        if self.expected_profit == 0.0 and self.net_edge_pct > 0:
            self.expected_profit = self.max_size * self.net_edge_pct
    
    @property
    def is_fresh(self) -> bool:
        """Check if price data is fresh (< 120 seconds)."""
        return self.freshness_seconds < 120
    
    @property
    def has_liquidity(self) -> bool:
        """Check if there's sufficient liquidity (> $10k)."""
        left_liq = self.left_leg.get("liquidity", 0)
        right_liq = self.right_leg.get("liquidity", 0)
        return left_liq >= 10000 and right_liq >= 10000
    
    @property
    def has_strong_match(self) -> bool:
        """Check if match confidence is strong (> 0.85)."""
        return self.match_score >= 0.85
    
    @property
    def net_edge_bps(self) -> float:
        """Net edge in basis points."""
        return self.net_edge_pct * 10000
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "arb_id": self.arb_id,
            "event_title": self.event_title,
            "left_leg": self.left_leg,
            "right_leg": self.right_leg,
            "gross_edge_pct": round(self.gross_edge_pct, 6),
            "fees_pct": round(self.fees_pct, 6),
            "slippage_pct": round(self.slippage_pct, 6),
            "net_edge_pct": round(self.net_edge_pct, 6),
            "max_size": round(self.max_size, 2),
            "expected_profit": round(self.expected_profit, 2),
            "match_score": round(self.match_score, 4),
            "resolution_confidence": round(self.resolution_confidence, 4),
            "freshness_seconds": self.freshness_seconds,
            "alertable": self.alertable,
            "discovered_at": self.discovered_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "passed_validation": self.passed_validation,
            "validation_errors": self.validation_errors,
        }
