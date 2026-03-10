"""Liquidity normalization across different market sources."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from .normalized_market_schema import LiquidityInfo, NormalizedMarket


@dataclass
class LiquidityScore:
    """Calculated liquidity score for a market."""

    score: Decimal  # 0-100
    confidence: Decimal  # 0-1, how confident we are in the score
    factors: dict[str, Decimal]  # Individual factor scores


class LiquidityNormalizer:
    """Normalizes liquidity metrics across Polymarket and sportsbooks.

    Different sources report liquidity differently:
    - Polymarket: volume, open_interest
    - Sportsbooks: implied from odds movement, limits (not directly available)

    This normalizer creates a consistent liquidity score.
    """

    # Volume thresholds for scoring (in USD)
    VOLUME_TIERS = {
        "micro": Decimal("10000"),  # $10k
        "small": Decimal("100000"),  # $100k
        "medium": Decimal("1000000"),  # $1M
        "large": Decimal("10000000"),  # $10M
    }

    # Scoring weights
    WEIGHTS = {
        "volume": Decimal("0.4"),
        "open_interest": Decimal("0.3"),
        "spread": Decimal("0.2"),
        "depth": Decimal("0.1"),
    }

    def __init__(self) -> None:
        """Initialize the normalizer."""
        self.scoring_history: list[LiquidityScore] = []

    def calculate_polymarket_score(
        self,
        market: NormalizedMarket,
    ) -> LiquidityScore:
        """Calculate liquidity score for Polymarket markets.

        Args:
            market: Normalized market from Polymarket

        Returns:
            Liquidity score
        """
        liq = market.liquidity
        factors: dict[str, Decimal] = {}

        # Volume score (0-100)
        volume = liq.total_volume or Decimal("0")
        if volume >= self.VOLUME_TIERS["large"]:
            factors["volume"] = Decimal("100")
        elif volume >= self.VOLUME_TIERS["medium"]:
            factors["volume"] = Decimal("75") + (
                (volume - self.VOLUME_TIERS["medium"])
                / (self.VOLUME_TIERS["large"] - self.VOLUME_TIERS["medium"])
                * Decimal("25")
            )
        elif volume >= self.VOLUME_TIERS["small"]:
            factors["volume"] = Decimal("50") + (
                (volume - self.VOLUME_TIERS["small"])
                / (self.VOLUME_TIERS["medium"] - self.VOLUME_TIERS["small"])
                * Decimal("25")
            )
        elif volume >= self.VOLUME_TIERS["micro"]:
            factors["volume"] = Decimal("25") + (
                (volume - self.VOLUME_TIERS["micro"])
                / (self.VOLUME_TIERS["small"] - self.VOLUME_TIERS["micro"])
                * Decimal("25")
            )
        else:
            factors["volume"] = (volume / self.VOLUME_TIERS["micro"]) * Decimal("25")

        # Open interest score
        if liq.open_interest:
            oi_ratio = liq.open_interest / (volume + Decimal("1"))
            # Higher OI relative to volume suggests more active positions
            factors["open_interest"] = min(oi_ratio * Decimal("100"), Decimal("100"))
        else:
            factors["open_interest"] = Decimal("50")  # Unknown, neutral

        # Spread score (tighter spread = higher score)
        if liq.bid_ask_spread is not None:
            # Spread is typically 0-0.1 (0-10%)
            spread = min(liq.bid_ask_spread, Decimal("0.1"))
            factors["spread"] = (Decimal("1") - (spread / Decimal("0.1"))) * Decimal("100")
        else:
            # Estimate spread from outcomes
            if len(market.outcomes) >= 2:
                probs = [o.probability for o in market.outcomes]
                total_prob = sum(probs)
                # If total > 1, there's a spread
                if total_prob > 1:
                    implied_spread = (total_prob - 1) / len(probs)
                    factors["spread"] = (
                        Decimal("1") - (implied_spread / Decimal("0.1"))
                    ) * Decimal("100")
                else:
                    factors["spread"] = Decimal("90")  # No vig assumed
            else:
                factors["spread"] = Decimal("50")

        # Depth score (use existing or calculate)
        if liq.depth_score is not None:
            factors["depth"] = liq.depth_score
        else:
            # Estimate from volume
            factors["depth"] = factors["volume"] * Decimal("0.8")

        # Calculate weighted total
        total_score = sum(
            factors[key] * self.WEIGHTS[key] for key in factors
        )

        # High confidence for Polymarket (direct data)
        confidence = Decimal("0.85")

        score = LiquidityScore(
            score=min(max(total_score, Decimal("0")), Decimal("100")),
            confidence=confidence,
            factors=factors,
        )
        self.scoring_history.append(score)
        return score

    def calculate_sportsbook_score(
        self,
        market: NormalizedMarket,
    ) -> LiquidityScore:
        """Calculate liquidity score for sportsbook markets.

        Sportsbooks don't expose volume directly, so we infer from:
        - Odds stability (implied)
        - Market type (major events have more liquidity)
        - Number of outcomes

        Args:
            market: Normalized market from sportsbook

        Returns:
            Liquidity score
        """
        factors: dict[str, Decimal] = {}

        # Base score from market characteristics
        # Major sportsbooks generally have high liquidity for major events
        base_score = Decimal("70")

        # Adjust based on event timing
        if market.start_time:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            time_to_event = market.start_time - now
            hours_to_event = time_to_event.total_seconds() / 3600

            if hours_to_event < 1:
                # Very close to event - typically high liquidity
                base_score = Decimal("85")
            elif hours_to_event < 24:
                base_score = Decimal("80")
            elif hours_to_event < 72:
                base_score = Decimal("75")
            else:
                base_score = Decimal("65")

        factors["market_timing"] = base_score

        # Odds quality (check for balanced book)
        if len(market.outcomes) >= 2:
            probs = [o.probability for o in market.outcomes]
            total_prob = sum(probs)

            # Vig calculation
            vig = total_prob - Decimal("1")
            if vig <= Decimal("0.02"):
                factors["odds_quality"] = Decimal("95")  # Very competitive
            elif vig <= Decimal("0.05"):
                factors["odds_quality"] = Decimal("85")
            elif vig <= Decimal("0.08"):
                factors["odds_quality"] = Decimal("75")
            else:
                factors["odds_quality"] = Decimal("60")
        else:
            factors["odds_quality"] = Decimal("50")

        # Market type score
        market_type_scores = {
            "moneyline": Decimal("90"),
            "spread": Decimal("85"),
            "totals": Decimal("80"),
            "props": Decimal("60"),
            "futures": Decimal("50"),
        }
        factors["market_type"] = Decimal("70")  # Default
        for tag in market.tags:
            tag_lower = tag.lower()
            if tag_lower in market_type_scores:
                factors["market_type"] = market_type_scores[tag_lower]
                break

        # Calculate total (different weights for sportsbooks)
        weights = {
            "market_timing": Decimal("0.4"),
            "odds_quality": Decimal("0.35"),
            "market_type": Decimal("0.25"),
        }

        total_score = sum(
            factors[key] * weights[key] for key in factors
        )

        # Lower confidence for sportsbooks (inferred data)
        confidence = Decimal("0.60")

        score = LiquidityScore(
            score=min(max(total_score, Decimal("0")), Decimal("100")),
            confidence=confidence,
            factors=factors,
        )
        self.scoring_history.append(score)
        return score

    def normalize(self, market: NormalizedMarket) -> LiquidityInfo:
        """Normalize liquidity for any market source.

        Args:
            market: Normalized market

        Returns:
            Updated liquidity info with normalized depth score
        """
        source = market.source.lower()

        if source == "polymarket":
            score = self.calculate_polymarket_score(market)
        elif source in {
            "draftkings",
            "fanduel",
            "bet365",
            "betmgm",
            "caesars",
            "bovada",
            "pinnacle",
            "williamhill",
            "unibet",
            "pointsbet",
        }:
            score = self.calculate_sportsbook_score(market)
        else:
            # Unknown source - use generic scoring
            score = self._calculate_generic_score(market)

        # Update liquidity info with normalized score
        return LiquidityInfo(
            total_volume=market.liquidity.total_volume,
            open_interest=market.liquidity.open_interest,
            bid_ask_spread=market.liquidity.bid_ask_spread,
            depth_score=score.score,
        )

    def _calculate_generic_score(self, market: NormalizedMarket) -> LiquidityScore:
        """Calculate generic score for unknown sources.

        Args:
            market: Normalized market

        Returns:
            Liquidity score
        """
        factors: dict[str, Decimal] = {
            "unknown_source": Decimal("50"),
        }

        if market.liquidity.total_volume:
            volume = market.liquidity.total_volume
            if volume > 1_000_000:
                factors["volume"] = Decimal("80")
            elif volume > 100_000:
                factors["volume"] = Decimal("60")
            else:
                factors["volume"] = Decimal("40")
        else:
            factors["volume"] = Decimal("30")

        # Very low confidence for unknown sources
        confidence = Decimal("0.40")

        score = LiquidityScore(
            score=Decimal("50"),
            confidence=confidence,
            factors=factors,
        )
        self.scoring_history.append(score)
        return score

    def compare_liquidity(
        self,
        market1: NormalizedMarket,
        market2: NormalizedMarket,
    ) -> dict[str, Any]:
        """Compare liquidity between two markets.

        Args:
            market1: First market
            market2: Second market

        Returns:
            Comparison results
        """
        score1 = self.normalize(market1)
        score2 = self.normalize(market2)

        return {
            "market1": {
                "source": market1.source,
                "depth_score": score1.depth_score,
            },
            "market2": {
                "source": market2.source,
                "depth_score": score2.depth_score,
            },
            "difference": (score1.depth_score or Decimal("0")) - (
                score2.depth_score or Decimal("0")
            ),
            "more_liquid": market1.source
            if (score1.depth_score or Decimal("0")) > (score2.depth_score or Decimal("0"))
            else market2.source,
        }

    def get_average_score(self) -> Decimal:
        """Get average liquidity score from history.

        Returns:
            Average score
        """
        if not self.scoring_history:
            return Decimal("0")
        total = sum(s.score for s in self.scoring_history)
        return total / len(self.scoring_history)

    def reset_history(self) -> None:
        """Clear scoring history."""
        self.scoring_history.clear()


def apply_liquidity_normalization(
    markets: list[NormalizedMarket],
) -> list[NormalizedMarket]:
    """Apply liquidity normalization to a list of markets.

    Args:
        markets: List of normalized markets

    Returns:
        Markets with normalized liquidity
    """
    normalizer = LiquidityNormalizer()
    result: list[NormalizedMarket] = []

    for market in markets:
        normalized_liq = normalizer.normalize(market)
        # Create new market with normalized liquidity
        updated = market.model_copy()
        updated.liquidity = normalized_liq
        result.append(updated)

    return result
