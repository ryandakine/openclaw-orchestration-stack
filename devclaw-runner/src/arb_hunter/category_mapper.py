"""Category mapping for consistent classification across sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .market_normalization_error import MarketNormalizationError
from .normalized_market_schema import Category, NormalizedMarket


@dataclass
class CategoryMapping:
    """Mapping result with confidence score."""

    category: Category
    confidence: float  # 0.0 to 1.0
    matched_keywords: list[str]
    method: str  # How the category was determined


class CategoryMapper:
    """Maps various category formats to canonical categories.

    Different sources use different category names:
    - Polymarket: "politics", "sports", "crypto", etc.
    - Sportsbooks: sport-based categories
    - Others: various taxonomies

    This provides consistent category mapping.
    """

    # Keyword patterns for each category
    CATEGORY_KEYWORDS: dict[Category, list[str]] = {
        Category.POLITICS: [
            "politics",
            "election",
            "president",
            "congress",
            "senate",
            "house",
            "vote",
            "ballot",
            "trump",
            "biden",
            "democrat",
            "republican",
            "gop",
            "white house",
            "campaign",
            "primary",
            "midterm",
            "governor",
            "mayor",
            "parliament",
            "brexit",
            "eu",
            "geopolitical",
        ],
        Category.SPORTS: [
            "sports",
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "soccer",
            "football",
            "basketball",
            "baseball",
            "hockey",
            "tennis",
            "golf",
            "mma",
            "ufc",
            "boxing",
            "olympics",
            "super bowl",
            "world cup",
            "premier league",
            "champions league",
            "nascar",
            "f1",
            "racing",
            "cricket",
            "rugby",
        ],
        Category.CRYPTO: [
            "crypto",
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "cryptocurrency",
            "blockchain",
            "defi",
            "nft",
            "altcoin",
            "token",
            "solana",
            "cardano",
            "binance",
            "coinbase",
            "wallet",
            "mining",
            "halving",
            "etf",
            "spot etf",
        ],
        Category.ECONOMICS: [
            "economics",
            "finance",
            "economy",
            "fed",
            "federal reserve",
            "interest rate",
            "inflation",
            "cpi",
            "gdp",
            "recession",
            "unemployment",
            "jobs report",
            "stock market",
            "sp500",
            "nasdaq",
            "dow",
            "earnings",
            "ipo",
            "bank",
            "treasury",
        ],
        Category.ENTERTAINMENT: [
            "entertainment",
            "pop culture",
            "celebrity",
            "movie",
            "film",
            "oscar",
            "emmy",
            "grammy",
            "academy awards",
            "box office",
            "music",
            "album",
            "song",
            "tv",
            "television",
            "streaming",
            "netflix",
            "disney",
            "marvel",
            "star wars",
            "kardashian",
            "taylor swift",
            "beyonce",
        ],
        Category.TECHNOLOGY: [
            "technology",
            "tech",
            "ai",
            "artificial intelligence",
            "machine learning",
            "google",
            "apple",
            "microsoft",
            "amazon",
            "meta",
            "facebook",
            "twitter",
            "x.com",
            "tesla",
            "spacex",
            "spacex",
            "rocket",
            "launch",
            "iphone",
            "android",
            "app",
            "software",
            "hardware",
        ],
        Category.SCIENCE: [
            "science",
            "space",
            "nasa",
            "mars",
            "moon",
            "climate",
            "weather",
            "temperature",
            "hurricane",
            "earthquake",
            "pandemic",
            "covid",
            "vaccine",
            "medical",
            "health",
            "research",
            "discovery",
            "physics",
            "chemistry",
            "biology",
        ],
    }

    def __init__(self) -> None:
        """Initialize the mapper."""
        self.mapping_history: list[tuple[str, CategoryMapping]] = []
        self.custom_rules: list[Callable[[str], CategoryMapping | None]] = []

    def add_custom_rule(
        self,
        rule: Callable[[str], CategoryMapping | None],
    ) -> None:
        """Add a custom mapping rule.

        Args:
            rule: Function that takes text and returns mapping or None
        """
        self.custom_rules.append(rule)

    def map_from_text(
        self,
        text: str,
        source_category: str | None = None,
    ) -> CategoryMapping:
        """Map category from text (title, description, etc.).

        Args:
            text: Text to analyze
            source_category: Optional source category hint

        Returns:
            Category mapping result
        """
        text_lower = text.lower()

        # Try custom rules first
        for rule in self.custom_rules:
            result = rule(text)
            if result:
                self.mapping_history.append((text, result))
                return result

        # Try source category hint
        if source_category:
            mapped = self._map_source_category(source_category)
            if mapped:
                return CategoryMapping(
                    category=mapped,
                    confidence=0.8,
                    matched_keywords=[source_category.lower()],
                    method="source_category",
                )

        # Keyword matching
        scores: dict[Category, list[str]] = {cat: [] for cat in Category}

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[category].append(keyword)

        # Find best match
        best_category = Category.OTHER
        best_keywords: list[str] = []
        max_matches = 0

        for category, matched in scores.items():
            if len(matched) > max_matches:
                max_matches = len(matched)
                best_category = category
                best_keywords = matched

        if max_matches > 0:
            confidence = min(0.5 + (max_matches * 0.1), 0.95)
            result = CategoryMapping(
                category=best_category,
                confidence=confidence,
                matched_keywords=best_keywords,
                method="keyword_match",
            )
        else:
            result = CategoryMapping(
                category=Category.OTHER,
                confidence=0.3,
                matched_keywords=[],
                method="default",
            )

        self.mapping_history.append((text, result))
        return result

    def _map_source_category(self, source_category: str) -> Category | None:
        """Map a source category string to canonical category.

        Args:
            source_category: Source category name

        Returns:
            Canonical category or None
        """
        source_lower = source_category.lower()

        # Direct mapping
        direct_map: dict[str, Category] = {
            "politics": Category.POLITICS,
            "sports": Category.SPORTS,
            "crypto": Category.CRYPTO,
            "bitcoin": Category.CRYPTO,
            "economics": Category.ECONOMICS,
            "finance": Category.ECONOMICS,
            "entertainment": Category.ENTERTAINMENT,
            "pop-culture": Category.ENTERTAINMENT,
            "technology": Category.TECHNOLOGY,
            "tech": Category.TECHNOLOGY,
            "science": Category.SCIENCE,
        }

        if source_lower in direct_map:
            return direct_map[source_lower]

        # Partial match
        for key, cat in direct_map.items():
            if key in source_lower or source_lower in key:
                return cat

        return None

    def map_market(self, market: NormalizedMarket) -> CategoryMapping:
        """Map category for a market.

        Args:
            market: Normalized market

        Returns:
            Category mapping
        """
        # Combine title and description for analysis
        text = market.title
        if market.description:
            text += " " + market.description

        # Include tags
        for tag in market.tags:
            text += " " + tag

        return self.map_from_text(text, str(market.category.value))

    def apply_to_market(
        self,
        market: NormalizedMarket,
        override: bool = False,
    ) -> NormalizedMarket:
        """Apply category mapping to a market.

        Args:
            market: Market to update
            override: Override existing category if OTHER

        Returns:
            Updated market
        """
        if market.category != Category.OTHER and not override:
            return market

        mapping = self.map_market(market)

        # Create updated market with new category
        updated = market.model_copy()
        updated.category = mapping.category

        # Add mapping info to tags
        if mapping.matched_keywords:
            for kw in mapping.matched_keywords[:3]:  # Limit to top 3
                if kw not in updated.tags:
                    updated.tags.append(kw)

        return updated

    def apply_to_markets(
        self,
        markets: list[NormalizedMarket],
        override: bool = False,
    ) -> list[NormalizedMarket]:
        """Apply category mapping to multiple markets.

        Args:
            markets: Markets to update
            override: Override existing categories

        Returns:
            Updated markets
        """
        return [self.apply_to_market(m, override) for m in markets]

    def get_mapping_stats(self) -> dict[str, int]:
        """Get category mapping statistics.

        Returns:
            Counts by category
        """
        stats: dict[str, int] = {cat.value: 0 for cat in Category}

        for _, mapping in self.mapping_history:
            stats[mapping.category.value] += 1

        return stats

    def get_confidence_distribution(self) -> dict[str, int]:
        """Get distribution of confidence scores.

        Returns:
            Counts by confidence range
        """
        ranges = {
            "high (0.8-1.0)": 0,
            "medium (0.5-0.8)": 0,
            "low (0.0-0.5)": 0,
        }

        for _, mapping in self.mapping_history:
            if mapping.confidence >= 0.8:
                ranges["high (0.8-1.0)"] += 1
            elif mapping.confidence >= 0.5:
                ranges["medium (0.5-0.8)"] += 1
            else:
                ranges["low (0.0-0.5)"] += 1

        return ranges

    def reset_history(self) -> None:
        """Clear mapping history."""
        self.mapping_history.clear()


# Pre-defined common mappings for quick lookup
QUICK_MAPPINGS: dict[str, Category] = {
    # Politics
    "us-election": Category.POLITICS,
    "presidential-election": Category.POLITICS,
    "congress": Category.POLITICS,
    "geopolitics": Category.POLITICS,
    # Sports
    "nba": Category.SPORTS,
    "nfl": Category.SPORTS,
    "mlb": Category.SPORTS,
    "nhl": Category.SPORTS,
    "soccer": Category.SPORTS,
    "football": Category.SPORTS,
    "mma": Category.SPORTS,
    # Crypto
    "btc": Category.CRYPTO,
    "eth": Category.CRYPTO,
    "defi": Category.CRYPTO,
    # Economics
    "macro": Category.ECONOMICS,
    "stocks": Category.ECONOMICS,
    "trading": Category.ECONOMICS,
}


def quick_map_category(text: str) -> Category:
    """Quick category mapping for known patterns.

    Args:
        text: Text to map

    Returns:
        Category
    """
    text_lower = text.lower()

    for pattern, category in QUICK_MAPPINGS.items():
        if pattern in text_lower:
            return category

    return Category.OTHER
