"""Transformer for sportsbook API responses to NormalizedMarket."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from .market_normalization_error import MarketNormalizationError
from .normalized_market_schema import (
    Category,
    LiquidityInfo,
    MarketType,
    NormalizedMarket,
    Outcome,
)


class SportsbookTransformer:
    """Transforms sportsbook odds API responses to NormalizedMarket format."""

    # Bookmaker name mapping
    BOOKMAKER_NAMES: dict[str, str] = {
        "draftkings": "draftkings",
        "fanduel": "fanduel",
        "bet365": "bet365",
        "betmgm": "betmgm",
        "caesars": "caesars",
        "bovada": "bovada",
        "pinnacle": "pinnacle",
        "williamhill": "williamhill",
        "unibet": "unibet",
        "pointsbetus": "pointsbet",
        "wynnbet": "wynnbet",
        "barstool": "barstool",
        "betrivers": "betrivers",
        "foxbet": "foxbet",
        "betfair": "betfair",
    }

    # Market type mapping
    MARKET_TYPE_MAP: dict[str, MarketType] = {
        "h2h": MarketType.BINARY,
        "spreads": MarketType.BINARY,
        "totals": MarketType.BINARY,
        "outrights": MarketType.MULTIPLE_CHOICE,
        "moneyline": MarketType.BINARY,
    }

    def __init__(self) -> None:
        """Initialize the transformer."""
        self.transformed_count = 0
        self.error_count = 0

    def _parse_timestamp(self, ts: str | int | None) -> datetime | None:
        """Parse timestamp from various formats.

        Args:
            ts: Timestamp string or unix timestamp

        Returns:
            Parsed datetime or None
        """
        if ts is None:
            return None

        try:
            if isinstance(ts, int):
                return datetime.utcfromtimestamp(ts)
            elif isinstance(ts, str):
                # ISO format
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, OSError):
            pass

        return None

    def _decimal_odds_to_probability(self, odds: float | Decimal) -> Decimal:
        """Convert decimal odds to implied probability.

        Args:
            odds: Decimal odds (e.g., 1.91)

        Returns:
            Implied probability (e.g., 0.524)
        """
        if odds <= 1:
            return Decimal("0.5")  # Invalid odds, return 50%
        return Decimal("1") / Decimal(str(odds))

    def _american_odds_to_probability(self, odds: int) -> Decimal:
        """Convert American odds to implied probability.

        Args:
            odds: American odds (e.g., -110 or +150)

        Returns:
            Implied probability
        """
        if odds > 0:
            # Positive odds: 100 / (odds + 100)
            return Decimal("100") / Decimal(str(odds + 100))
        else:
            # Negative odds: abs(odds) / (abs(odds) + 100)
            return Decimal(str(abs(odds))) / Decimal(str(abs(odds) + 100))

    def _normalize_bookmaker_name(self, key: str) -> str:
        """Normalize bookmaker key to standard name.

        Args:
            key: Raw bookmaker key

        Returns:
            Normalized name
        """
        key_lower = key.lower()
        return self.BOOKMAKER_NAMES.get(key_lower, key_lower)

    def _extract_moneyline_outcomes(
        self,
        market_data: dict[str, Any],
        home_team: str,
        away_team: str,
    ) -> list[Outcome]:
        """Extract outcomes from moneyline/h2h market.

        Args:
            market_data: Market data with outcomes
            home_team: Home team name
            away_team: Away team name

        Returns:
            List of normalized outcomes
        """
        outcomes: list[Outcome] = []
        raw_outcomes = market_data.get("outcomes", [])

        for outcome in raw_outcomes:
            name = outcome.get("name", "")
            price = outcome.get("price")

            # Map team names to Yes/No for binary representation
            # Or keep team names for clarity
            if name == home_team:
                display_name = f"{home_team} (Home)"
            elif name == away_team:
                display_name = f"{away_team} (Away)"
            else:
                display_name = name

            # Calculate probability from odds
            if isinstance(price, (int, float, str)):
                try:
                    decimal_price = Decimal(str(price))
                    # Determine if American or decimal
                    if decimal_price > 100 or decimal_price < -100:
                        # American odds
                        probability = self._american_odds_to_probability(int(decimal_price))
                    else:
                        # Decimal odds
                        probability = self._decimal_odds_to_probability(decimal_price)
                except (ValueError, InvalidOperation):
                    probability = Decimal("0.5")
            else:
                probability = Decimal("0.5")

            outcomes.append(
                Outcome(
                    name=display_name,
                    probability=probability,
                    price=self._parse_decimal(price),
                )
            )

        return outcomes

    def _extract_spread_outcomes(
        self,
        market_data: dict[str, Any],
        home_team: str,
        away_team: str,
    ) -> list[Outcome]:
        """Extract outcomes from spread market.

        Args:
            market_data: Market data
            home_team: Home team name
            away_team: Away team name

        Returns:
            List of normalized outcomes
        """
        outcomes: list[Outcome] = []
        point = market_data.get("point")
        raw_outcomes = market_data.get("outcomes", [])

        for outcome in raw_outcomes:
            name = outcome.get("name", "")
            price = outcome.get("price")

            # Add spread info to name
            if point is not None:
                if name == home_team:
                    display_name = f"{home_team} {point}"
                elif name == away_team:
                    display_name = f"{away_team} {float(point) * -1:+.1f}"
                else:
                    display_name = name
            else:
                display_name = name

            if isinstance(price, (int, float, str)):
                try:
                    decimal_price = Decimal(str(price))
                    if decimal_price > 100 or decimal_price < -100:
                        probability = self._american_odds_to_probability(int(decimal_price))
                    else:
                        probability = self._decimal_odds_to_probability(decimal_price)
                except (ValueError, InvalidOperation):
                    probability = Decimal("0.5")
            else:
                probability = Decimal("0.5")

            outcomes.append(
                Outcome(
                    name=display_name,
                    probability=probability,
                    price=self._parse_decimal(price),
                )
            )

        return outcomes

    def _extract_totals_outcomes(
        self,
        market_data: dict[str, Any],
    ) -> list[Outcome]:
        """Extract outcomes from totals (over/under) market.

        Args:
            market_data: Market data

        Returns:
            List of normalized outcomes (Over/Under)
        """
        outcomes: list[Outcome] = []
        point = market_data.get("point")
        raw_outcomes = market_data.get("outcomes", [])

        for outcome in raw_outcomes:
            name = outcome.get("name", "")
            price = outcome.get("price")

            # Format as Over/Under with line
            if point is not None:
                if "over" in name.lower():
                    display_name = f"Over {point}"
                elif "under" in name.lower():
                    display_name = f"Under {point}"
                else:
                    display_name = name
            else:
                display_name = name

            if isinstance(price, (int, float, str)):
                try:
                    decimal_price = Decimal(str(price))
                    if decimal_price > 100 or decimal_price < -100:
                        probability = self._american_odds_to_probability(int(decimal_price))
                    else:
                        probability = self._decimal_odds_to_probability(decimal_price)
                except (ValueError, InvalidOperation):
                    probability = Decimal("0.5")
            else:
                probability = Decimal("0.5")

            outcomes.append(
                Outcome(
                    name=display_name,
                    probability=probability,
                    price=self._parse_decimal(price),
                )
            )

        return outcomes

    def _parse_decimal(self, value: Any) -> Decimal | None:
        """Safely parse decimal value.

        Args:
            value: Value to parse

        Returns:
            Decimal or None
        """
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None

    def transform_bookmaker_odds(
        self,
        event_data: dict[str, Any],
        bookmaker_data: dict[str, Any],
        sport: str,
    ) -> list[NormalizedMarket]:
        """Transform a single bookmaker's odds for an event.

        Args:
            event_data: Event information
            bookmaker_data: Bookmaker odds data
            sport: Sport key

        Returns:
            List of normalized markets (one per market type)
        """
        markets: list[NormalizedMarket] = []

        event_id = event_data.get("id", "")
        home_team = event_data.get("home_team", "")
        away_team = event_data.get("away_team", "")
        commence_time = self._parse_timestamp(event_data.get("commence_time"))

        bookmaker_key = bookmaker_data.get("key", "")
        bookmaker_title = bookmaker_data.get("title", bookmaker_key)
        source = self._normalize_bookmaker_name(bookmaker_key)
        last_update = self._parse_timestamp(bookmaker_data.get("last_update"))

        # Process each market type
        for market in bookmaker_data.get("markets", []):
            market_key = market.get("key", "")

            try:
                # Determine market type
                market_type = self.MARKET_TYPE_MAP.get(market_key, MarketType.BINARY)

                # Extract outcomes based on market type
                if market_key == "h2h":
                    outcomes = self._extract_moneyline_outcomes(
                        market, home_team, away_team
                    )
                    title = f"{away_team} @ {home_team} - Moneyline"
                elif market_key == "spreads":
                    outcomes = self._extract_spread_outcomes(market, home_team, away_team)
                    point = market.get("point", "?")
                    title = f"{away_team} @ {home_team} - Spread {point}"
                elif market_key == "totals":
                    outcomes = self._extract_totals_outcomes(market)
                    point = market.get("point", "?")
                    title = f"{away_team} @ {home_team} - Total {point}"
                else:
                    # Generic handling
                    outcomes = self._extract_moneyline_outcomes(
                        market, home_team, away_team
                    )
                    title = f"{away_team} @ {home_team} - {market_key}"

                if not outcomes:
                    continue

                # Build URL (bookmaker-specific)
                url = self._build_bookmaker_url(source, event_id, home_team, away_team)

                normalized = NormalizedMarket(
                    source=source,
                    source_event_id=event_id,
                    title=title,
                    market_type=market_type,
                    category=Category.SPORTS,
                    start_time=commence_time,
                    outcomes=outcomes,
                    liquidity=LiquidityInfo(),  # Sportsbooks don't expose this easily
                    url=url,
                    tags=[sport, market_key, bookmaker_title],
                    source_timestamp=last_update,
                )

                markets.append(normalized)
                self.transformed_count += 1

            except Exception as e:
                self.error_count += 1
                # Continue with other markets
                continue

        return markets

    def _build_bookmaker_url(
        self,
        bookmaker: str,
        event_id: str,
        home_team: str,
        away_team: str,
    ) -> str | None:
        """Build a URL to the bookmaker's event page.

        Args:
            bookmaker: Bookmaker name
            event_id: Event ID
            home_team: Home team
            away_team: Away team

        Returns:
            URL or None
        """
        # These are generic patterns - actual URLs would require deep linking
        bookmaker_urls: dict[str, str] = {
            "draftkings": "https://sportsbook.draftkings.com/",
            "fanduel": "https://sportsbook.fanduel.com/",
            "bet365": "https://www.bet365.com/",
            "betmgm": "https://sports.betmgm.com/",
            "caesars": "https://sportsbook.caesars.com/",
        }

        return bookmaker_urls.get(bookmaker)

    def transform_event(
        self,
        event_data: dict[str, Any],
        sport: str,
        target_bookmakers: set[str] | None = None,
    ) -> list[NormalizedMarket]:
        """Transform all bookmaker odds for an event.

        Args:
            event_data: Event data from Odds API
            sport: Sport key
            target_bookmakers: Filter by specific bookmakers

        Returns:
            List of normalized markets
        """
        all_markets: list[NormalizedMarket] = []

        for bookmaker in event_data.get("bookmakers", []):
            bookmaker_key = bookmaker.get("key", "").lower()

            if target_bookmakers and bookmaker_key not in target_bookmakers:
                continue

            try:
                markets = self.transform_bookmaker_odds(event_data, bookmaker, sport)
                all_markets.extend(markets)
            except MarketNormalizationError:
                continue

        return all_markets

    def transform_many_events(
        self,
        events: list[dict[str, Any]],
        sport: str,
        target_bookmakers: set[str] | None = None,
    ) -> list[NormalizedMarket]:
        """Transform multiple events.

        Args:
            events: List of event data
            sport: Sport key
            target_bookmakers: Filter by bookmakers

        Returns:
            List of normalized markets
        """
        all_markets: list[NormalizedMarket] = []

        for event in events:
            try:
                markets = self.transform_event(event, sport, target_bookmakers)
                all_markets.extend(markets)
            except MarketNormalizationError:
                continue

        return all_markets

    def get_stats(self) -> dict[str, int]:
        """Get transformation statistics.

        Returns:
            Dict with counts
        """
        return {
            "transformed_count": self.transformed_count,
            "error_count": self.error_count,
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self.transformed_count = 0
        self.error_count = 0
