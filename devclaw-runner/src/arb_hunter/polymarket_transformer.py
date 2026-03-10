"""Transformer for Polymarket API responses to NormalizedMarket."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .market_normalization_error import MarketNormalizationError
from .normalized_market_schema import (
    Category,
    LiquidityInfo,
    MarketType,
    NormalizedMarket,
    Outcome,
)


class PolymarketTransformer:
    """Transforms Polymarket API responses to NormalizedMarket format."""

    # Category mapping from Polymarket slugs to canonical categories
    CATEGORY_MAP: dict[str, Category] = {
        "politics": Category.POLITICS,
        "sports": Category.SPORTS,
        "crypto": Category.CRYPTO,
        "bitcoin": Category.CRYPTO,
        "ethereum": Category.CRYPTO,
        "economics": Category.ECONOMICS,
        "finance": Category.ECONOMICS,
        "entertainment": Category.ENTERTAINMENT,
        "pop-culture": Category.ENTERTAINMENT,
        "technology": Category.TECHNOLOGY,
        "science": Category.SCIENCE,
        "other": Category.OTHER,
        "misc": Category.OTHER,
    }

    def __init__(self) -> None:
        """Initialize the transformer."""
        self.transformed_count = 0
        self.error_count = 0

    def _parse_timestamp(self, ts: str | int | float | None) -> datetime | None:
        """Parse various timestamp formats.

        Args:
            ts: Timestamp in various formats

        Returns:
            Parsed datetime or None
        """
        if ts is None:
            return None

        try:
            if isinstance(ts, (int, float)):
                # Unix timestamp (seconds or milliseconds)
                if ts > 1e10:  # Milliseconds
                    ts = ts / 1000
                return datetime.utcfromtimestamp(ts)
            elif isinstance(ts, str):
                # ISO format or other string format
                # Try ISO first
                if "T" in ts or "Z" in ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                # Try unix timestamp string
                try:
                    ts_num = float(ts)
                    if ts_num > 1e10:
                        ts_num = ts_num / 1000
                    return datetime.utcfromtimestamp(ts_num)
                except ValueError:
                    pass
        except (ValueError, OSError, OverflowError):
            pass

        return None

    def _parse_decimal(self, value: str | float | int | None) -> Decimal | None:
        """Safely parse a decimal value.

        Args:
            value: Value to parse

        Returns:
            Decimal or None
        """
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _parse_outcome_prices(self, outcome_prices: str | list | None) -> list[Decimal]:
        """Parse outcomePrices field which can be JSON string or list.

        Args:
            outcome_prices: Raw outcome prices

        Returns:
            List of price decimals
        """
        if outcome_prices is None:
            return []

        prices: list[Decimal] = []

        try:
            if isinstance(outcome_prices, str):
                # It's a JSON string
                parsed = json.loads(outcome_prices)
            else:
                parsed = outcome_prices

            if isinstance(parsed, list):
                for p in parsed:
                    dec = self._parse_decimal(p)
                    if dec is not None:
                        prices.append(dec)
            elif isinstance(parsed, dict):
                # Sometimes it's a dict with outcome names as keys
                for p in parsed.values():
                    dec = self._parse_decimal(p)
                    if dec is not None:
                        prices.append(dec)
        except json.JSONDecodeError:
            pass

        return prices

    def _map_category(self, category_slug: str | None) -> Category:
        """Map Polymarket category to canonical category.

        Args:
            category_slug: Polymarket category slug

        Returns:
            Canonical category
        """
        if not category_slug:
            return Category.OTHER

        slug_lower = category_slug.lower()

        # Direct match
        if slug_lower in self.CATEGORY_MAP:
            return self.CATEGORY_MAP[slug_lower]

        # Partial match
        for key, cat in self.CATEGORY_MAP.items():
            if key in slug_lower or slug_lower in key:
                return cat

        return Category.OTHER

    def _determine_market_type(self, outcomes: list[dict[str, Any]]) -> MarketType:
        """Determine market type from outcomes.

        Args:
            outcomes: Raw outcome data

        Returns:
            Market type
        """
        if not outcomes:
            return MarketType.BINARY

        outcome_names = [o.get("name", "").lower() for o in outcomes]

        # Binary check (Yes/No)
        yes_no = {"yes", "no"}
        if set(outcome_names) == yes_no:
            return MarketType.BINARY

        # Multiple choice (more than 2 outcomes)
        if len(outcomes) > 2:
            return MarketType.MULTIPLE_CHOICE

        return MarketType.BINARY

    def _extract_outcomes(
        self,
        market_data: dict[str, Any],
        market_type: MarketType,
    ) -> list[Outcome]:
        """Extract and normalize outcomes.

        Args:
            market_data: Raw market data
            market_type: Determined market type

        Returns:
            List of normalized outcomes
        """
        outcomes: list[Outcome] = []

        # Try to get outcomes from different possible locations
        raw_outcomes = market_data.get("outcomes", [])
        outcome_prices = self._parse_outcome_prices(market_data.get("outcomePrices"))

        if not raw_outcomes and "outcomePrices" in market_data:
            # Create outcomes from prices if names not available
            for i, price in enumerate(outcome_prices):
                name = "Yes" if i == 0 else "No" if i == 1 else f"Outcome {i + 1}"
                probability = price if price <= 1 else price / 100
                outcomes.append(
                    Outcome(
                        name=name,
                        probability=probability,
                        price=price,
                    )
                )
            return outcomes

        # Process raw outcomes
        for i, outcome in enumerate(raw_outcomes):
            if isinstance(outcome, dict):
                name = outcome.get("name", f"Outcome {i + 1}")
                price = self._parse_decimal(outcome.get("price"))

                # Get probability from various sources
                prob = self._parse_decimal(outcome.get("probability"))
                if prob is None and price is not None:
                    prob = price if price <= 1 else price / 100
                elif prob is None and i < len(outcome_prices):
                    prob = outcome_prices[i]
                    if prob > 1:
                        prob = prob / 100

                if prob is None:
                    prob = Decimal("0.5")  # Default

                volume = self._parse_decimal(outcome.get("volume"))

                outcomes.append(
                    Outcome(
                        name=name,
                        probability=prob,
                        price=price,
                        volume=volume,
                    )
                )
            else:
                # Outcome is just a string name
                name = str(outcome)
                price = outcome_prices[i] if i < len(outcome_prices) else None
                prob = price if price and price <= 1 else (
                    price / 100 if price else Decimal("0.5")
                )
                outcomes.append(
                    Outcome(
                        name=name,
                        probability=prob,
                        price=price,
                    )
                )

        return outcomes

    def _extract_liquidity(self, market_data: dict[str, Any]) -> LiquidityInfo:
        """Extract liquidity information.

        Args:
            market_data: Raw market data

        Returns:
            Normalized liquidity info
        """
        volume = self._parse_decimal(market_data.get("volume"))
        if volume is None:
            volume = self._parse_decimal(market_data.get("totalVolume"))

        open_interest = self._parse_decimal(market_data.get("openInterest"))

        # Calculate depth score based on volume
        depth_score: Decimal | None = None
        if volume is not None:
            # Simple heuristic: higher volume = higher depth score
            # Scale: $0 = 0, $1M+ = 100
            if volume >= 1_000_000:
                depth_score = Decimal("100")
            else:
                depth_score = (volume / 1_000_000) * 100

        # Bid-ask spread from spread field or calculate from outcomes
        spread = self._parse_decimal(market_data.get("spread"))

        return LiquidityInfo(
            total_volume=volume,
            open_interest=open_interest,
            bid_ask_spread=spread,
            depth_score=depth_score,
        )

    def transform(self, market_data: dict[str, Any]) -> NormalizedMarket:
        """Transform Polymarket market data to NormalizedMarket.

        Args:
            market_data: Raw market data from Polymarket API

        Returns:
            Normalized market

        Raises:
            MarketNormalizationError: If transformation fails
        """
        try:
            # Required fields
            market_id = str(market_data.get("id", market_data.get("conditionId", "")))
            if not market_id:
                raise MarketNormalizationError(
                    "Market missing ID",
                    source="polymarket",
                    raw_data=market_data,
                )

            title = market_data.get("question", market_data.get("title", ""))
            if not title:
                raise MarketNormalizationError(
                    f"Market {market_id} missing title",
                    source="polymarket",
                    raw_data=market_data,
                )

            # Determine market type
            raw_outcomes = market_data.get("outcomes", [])
            market_type = self._determine_market_type(raw_outcomes)

            # Extract outcomes
            outcomes = self._extract_outcomes(market_data, market_type)
            if not outcomes:
                raise MarketNormalizationError(
                    f"Market {market_id} has no valid outcomes",
                    source="polymarket",
                    raw_data=market_data,
                )

            # Category
            category_slug = market_data.get("category", market_data.get("slug", ""))
            category = self._map_category(category_slug)

            # Timestamps
            resolution_time = self._parse_timestamp(
                market_data.get("resolutionTime")
                or market_data.get("endDate")
                or market_data.get("expirationDate")
            )
            start_time = self._parse_timestamp(market_data.get("startDate"))
            source_timestamp = self._parse_timestamp(
                market_data.get("updatedAt") or market_data.get("timestamp")
            )

            # Liquidity
            liquidity = self._extract_liquidity(market_data)

            # URL
            slug = market_data.get("slug", "")
            url = f"https://polymarket.com/event/{slug}" if slug else None

            # Image
            image_url = market_data.get("image") or market_data.get("icon")

            # Tags
            tags: list[str] = []
            if category_slug:
                tags.append(category_slug)
            if market_data.get("tag"):
                tags.append(str(market_data.get("tag")))

            self.transformed_count += 1

            return NormalizedMarket(
                source="polymarket",
                source_event_id=market_id,
                source_market_id=market_data.get("conditionId"),
                title=title,
                description=market_data.get("description"),
                market_type=market_type,
                category=category,
                start_time=start_time,
                resolution_time=resolution_time,
                outcomes=outcomes,
                liquidity=liquidity,
                url=url,
                image_url=image_url,
                tags=tags,
                raw_source_data=market_data if False else None,  # Don't store raw by default
                source_timestamp=source_timestamp,
            )

        except MarketNormalizationError:
            self.error_count += 1
            raise
        except Exception as e:
            self.error_count += 1
            raise MarketNormalizationError(
                f"Unexpected error transforming market: {e}",
                source="polymarket",
                raw_data=market_data,
            ) from e

    def transform_many(
        self,
        markets_data: list[dict[str, Any]],
    ) -> list[NormalizedMarket]:
        """Transform multiple markets.

        Args:
            markets_data: List of raw market data

        Returns:
            List of normalized markets (failures are skipped)
        """
        results: list[NormalizedMarket] = []

        for data in markets_data:
            try:
                normalized = self.transform(data)
                results.append(normalized)
            except MarketNormalizationError:
                # Skip failed markets but continue processing
                continue

        return results

    def get_stats(self) -> dict[str, int]:
        """Get transformation statistics.

        Returns:
            Dict with transformed_count and error_count
        """
        return {
            "transformed_count": self.transformed_count,
            "error_count": self.error_count,
        }

    def reset_stats(self) -> None:
        """Reset transformation statistics."""
        self.transformed_count = 0
        self.error_count = 0
