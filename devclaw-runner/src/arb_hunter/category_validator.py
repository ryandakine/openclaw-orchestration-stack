"""
Category Validator - Verify event categories match across sources.

Module 2.5: Early rejection for category mismatches (politics≠sports).
Provides category normalization and cross-source mapping.
"""

import os
from enum import Enum
from typing import Optional


class Category(str, Enum):
    """Standardized event categories."""
    POLITICS = "politics"
    SPORTS = "sports"
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    BASEBALL = "baseball"
    SOCCER = "soccer"
    HOCKEY = "hockey"
    MMA = "mma"
    TENNIS = "tennis"
    GOLF = "golf"
    RACING = "racing"
    CRYPTO = "crypto"
    FINANCE = "finance"
    ENTERTAINMENT = "entertainment"
    TECHNOLOGY = "technology"
    SCIENCE = "science"
    WEATHER = "weather"
    UNKNOWN = "unknown"


class CategoryCompatibility(Enum):
    """Compatibility levels between categories."""
    IDENTICAL = 1.0
    RELATED = 0.7
    DIFFERENT_DOMAIN = 0.3
    INCOMPATIBLE = 0.0


class CategoryValidator:
    """Validates and matches event categories across sources."""
    
    # Category aliases from various sources
    CATEGORY_ALIASES: dict[str, Category] = {
        # Politics
        "politics": Category.POLITICS,
        "election": Category.POLITICS,
        "government": Category.POLITICS,
        "political": Category.POLITICS,
        
        # Sports
        "sports": Category.SPORTS,
        "sport": Category.SPORTS,
        "athletic": Category.SPORTS,
        
        # Football
        "football": Category.FOOTBALL,
        "nfl": Category.FOOTBALL,
        "cfb": Category.FOOTBALL,
        "college football": Category.FOOTBALL,
        
        # Basketball
        "basketball": Category.BASKETBALL,
        "nba": Category.BASKETBALL,
        "cbb": Category.BASKETBALL,
        "ncaa basketball": Category.BASKETBALL,
        "college basketball": Category.BASKETBALL,
        
        # Baseball
        "baseball": Category.BASEBALL,
        "mlb": Category.BASEBALL,
        
        # Soccer
        "soccer": Category.SOCCER,
        "football (soccer)": Category.SOCCER,
        "futbol": Category.SOCCER,
        "epl": Category.SOCCER,
        "premier league": Category.SOCCER,
        "la liga": Category.SOCCER,
        "bundesliga": Category.SOCCER,
        "serie a": Category.SOCCER,
        "ligue 1": Category.SOCCER,
        "mls": Category.SOCCER,
        "uefa": Category.SOCCER,
        "champions league": Category.SOCCER,
        "world cup": Category.SOCCER,
        
        # Hockey
        "hockey": Category.HOCKEY,
        "nhl": Category.HOCKEY,
        "ice hockey": Category.HOCKEY,
        
        # MMA
        "mma": Category.MMA,
        "ufc": Category.MMA,
        "boxing": Category.MMA,
        "wrestling": Category.MMA,
        "bellator": Category.MMA,
        
        # Tennis
        "tennis": Category.TENNIS,
        "atp": Category.TENNIS,
        "wta": Category.TENNIS,
        "grand slam": Category.TENNIS,
        "wimbledon": Category.TENNIS,
        "us open": Category.TENNIS,
        "french open": Category.TENNIS,
        "australian open": Category.TENNIS,
        
        # Golf
        "golf": Category.GOLF,
        "pga": Category.GOLF,
        "pga tour": Category.GOLF,
        "masters": Category.GOLF,
        "open championship": Category.GOLF,
        
        # Racing
        "racing": Category.RACING,
        "formula 1": Category.RACING,
        "f1": Category.RACING,
        "nascar": Category.RACING,
        "motorsport": Category.RACING,
        "motogp": Category.RACING,
        
        # Crypto
        "crypto": Category.CRYPTO,
        "cryptocurrency": Category.CRYPTO,
        "bitcoin": Category.CRYPTO,
        "blockchain": Category.CRYPTO,
        "defi": Category.CRYPTO,
        
        # Finance
        "finance": Category.FINANCE,
        "financial": Category.FINANCE,
        "stock market": Category.FINANCE,
        "trading": Category.FINANCE,
        "economy": Category.FINANCE,
        "economic": Category.FINANCE,
        
        # Entertainment
        "entertainment": Category.ENTERTAINMENT,
        "awards": Category.ENTERTAINMENT,
        "oscars": Category.ENTERTAINMENT,
        "grammys": Category.ENTERTAINMENT,
        "emmys": Category.ENTERTAINMENT,
        "movie": Category.ENTERTAINMENT,
        "tv": Category.ENTERTAINMENT,
        
        # Technology
        "technology": Category.TECHNOLOGY,
        "tech": Category.TECHNOLOGY,
        "ai": Category.TECHNOLOGY,
        "artificial intelligence": Category.TECHNOLOGY,
        
        # Science
        "science": Category.SCIENCE,
        "space": Category.SCIENCE,
        "nasa": Category.SCIENCE,
        
        # Weather
        "weather": Category.WEATHER,
        "hurricane": Category.WEATHER,
        "storm": Category.WEATHER,
    }
    
    # Related categories (can match with reduced confidence)
    RELATED_CATEGORIES: dict[Category, set[Category]] = {
        Category.SPORTS: {
            Category.FOOTBALL, Category.BASKETBALL, Category.BASEBALL,
            Category.SOCCER, Category.HOCKEY, Category.MMA, Category.TENNIS,
            Category.GOLF, Category.RACING,
        },
        Category.FOOTBALL: {Category.SPORTS},
        Category.BASKETBALL: {Category.SPORTS},
        Category.BASEBALL: {Category.SPORTS},
        Category.SOCCER: {Category.SPORTS},
        Category.HOCKEY: {Category.SPORTS},
        Category.MMA: {Category.SPORTS},
        Category.TENNIS: {Category.SPORTS},
        Category.GOLF: {Category.SPORTS},
        Category.RACING: {Category.SPORTS},
        Category.CRYPTO: {Category.FINANCE, Category.TECHNOLOGY},
        Category.FINANCE: {Category.CRYPTO, Category.ECONOMY} if hasattr(Category, 'ECONOMY') else {Category.CRYPTO},
        Category.TECHNOLOGY: {Category.CRYPTO, Category.SCIENCE},
        Category.SCIENCE: {Category.TECHNOLOGY},
    }
    
    # Incompatible category pairs (hard reject)
    INCOMPATIBLE_PAIRS: set[tuple[Category, Category]] = {
        (Category.POLITICS, Category.SPORTS),
        (Category.POLITICS, Category.FOOTBALL),
        (Category.POLITICS, Category.BASKETBALL),
        (Category.POLITICS, Category.SOCCER),
        (Category.POLITICS, Category.ENTERTAINMENT),
        (Category.POLITICS, Category.CRYPTO),
        (Category.SPORTS, Category.POLITICS),
        (Category.FOOTBALL, Category.POLITICS),
        (Category.BASKETBALL, Category.POLITICS),
        (Category.SOCCER, Category.POLITICS),
        (Category.ENTERTAINMENT, Category.POLITICS),
        (Category.CRYPTO, Category.POLITICS),
        (Category.SPORTS, Category.POLITICS),
        (Category.CRYPTO, Category.SPORTS),
        (Category.SPORTS, Category.CRYPTO),
        (Category.FINANCE, Category.SPORTS),
        (Category.SPORTS, Category.FINANCE),
    }
    
    def __init__(self) -> None:
        self.strict_mode = os.getenv("OPENCLAW_CATEGORY_STRICT", "true").lower() == "true"
        self.min_score = float(os.getenv("OPENCLAW_CATEGORY_MIN_SCORE", "0.5"))
    
    def normalize(self, category: str) -> Category:
        """
        Normalize a category string to standard Category enum.
        
        Args:
            category: Raw category string from source
        
        Returns:
            Standardized Category enum value
        """
        if not category:
            return Category.UNKNOWN
        
        # Direct match
        category_lower = category.lower().strip()
        try:
            return Category(category_lower)
        except ValueError:
            pass
        
        # Alias match
        if category_lower in self.CATEGORY_ALIASES:
            return self.CATEGORY_ALIASES[category_lower]
        
        # Partial match
        for alias, std_cat in self.CATEGORY_ALIASES.items():
            if alias in category_lower or category_lower in alias:
                return std_cat
        
        return Category.UNKNOWN
    
    def validate(
        self,
        category1: str,
        category2: str,
    ) -> tuple[float, CategoryCompatibility]:
        """
        Validate if two categories are compatible.
        
        Args:
            category1: First category string
            category2: Second category string
        
        Returns:
            Tuple of (score, compatibility_level)
        """
        norm1 = self.normalize(category1)
        norm2 = self.normalize(category2)
        
        # Identical categories
        if norm1 == norm2:
            return (1.0, CategoryCompatibility.IDENTICAL)
        
        # Check incompatible pairs (hard reject in strict mode)
        if (norm1, norm2) in self.INCOMPATIBLE_PAIRS:
            return (0.0, CategoryCompatibility.INCOMPATIBLE)
        
        # Check related categories
        if norm2 in self.RELATED_CATEGORIES.get(norm1, set()):
            return (0.7, CategoryCompatibility.RELATED)
        
        if norm1 in self.RELATED_CATEGORIES.get(norm2, set()):
            return (0.7, CategoryCompatibility.RELATED)
        
        # Different domains
        if self._is_different_domain(norm1, norm2):
            return (0.3, CategoryCompatibility.DIFFERENT_DOMAIN)
        
        return (0.5, CategoryCompatibility.DIFFERENT_DOMAIN)
    
    def is_compatible(
        self,
        category1: str,
        category2: str,
        min_score: Optional[float] = None,
    ) -> bool:
        """
        Quick check if categories are compatible.
        
        Args:
            category1: First category string
            category2: Second category string
            min_score: Optional override for minimum score
        
        Returns:
            True if categories are compatible
        """
        score, compatibility = self.validate(category1, category2)
        threshold = min_score if min_score is not None else self.min_score
        
        if self.strict_mode and compatibility == CategoryCompatibility.INCOMPATIBLE:
            return False
        
        return score >= threshold
    
    def should_reject_early(
        self,
        category1: str,
        category2: str,
    ) -> tuple[bool, str]:
        """
        Check if match should be rejected early due to category mismatch.
        
        Returns:
            Tuple of (should_reject, reason)
        """
        norm1 = self.normalize(category1)
        norm2 = self.normalize(category2)
        
        # Hard reject for known incompatible pairs
        if (norm1, norm2) in self.INCOMPATIBLE_PAIRS:
            return (True, f"Incompatible categories: {category1} vs {category2}")
        
        # Reject in strict mode for different domains
        if self.strict_mode:
            score, compat = self.validate(category1, category2)
            if compat == CategoryCompatibility.DIFFERENT_DOMAIN:
                return (True, f"Different domains: {category1} vs {category2}")
        
        return (False, "")
    
    def _is_different_domain(self, cat1: Category, cat2: Category) -> bool:
        """Check if two categories are in different high-level domains."""
        domains = {
            Category.POLITICS: "politics",
            Category.SPORTS: "sports",
            Category.FOOTBALL: "sports",
            Category.BASKETBALL: "sports",
            Category.BASEBALL: "sports",
            Category.SOCCER: "sports",
            Category.HOCKEY: "sports",
            Category.MMA: "sports",
            Category.TENNIS: "sports",
            Category.GOLF: "sports",
            Category.RACING: "sports",
            Category.CRYPTO: "finance",
            Category.FINANCE: "finance",
            Category.ENTERTAINMENT: "entertainment",
            Category.TECHNOLOGY: "technology",
            Category.SCIENCE: "science",
            Category.WEATHER: "science",
        }
        
        domain1 = domains.get(cat1, "unknown")
        domain2 = domains.get(cat2, "unknown")
        
        return domain1 != domain2
    
    def get_parent_category(self, category: str) -> Category:
        """Get the parent category for a specific sport/category."""
        norm = self.normalize(category)
        
        if norm in {
            Category.FOOTBALL, Category.BASKETBALL, Category.BASEBALL,
            Category.SOCCER, Category.HOCKEY, Category.MMA,
            Category.TENNIS, Category.GOLF, Category.RACING,
        }:
            return Category.SPORTS
        
        return norm


# Singleton instance
_default_validator: Optional[CategoryValidator] = None


def get_validator() -> CategoryValidator:
    """Get the default category validator instance."""
    global _default_validator
    if _default_validator is None:
        _default_validator = CategoryValidator()
    return _default_validator


def validate_categories(category1: str, category2: str) -> tuple[float, CategoryCompatibility]:
    """Convenience function to validate category compatibility."""
    return get_validator().validate(category1, category2)


def normalize_category(category: str) -> Category:
    """Convenience function to normalize a category."""
    return get_validator().normalize(category)


def are_compatible(category1: str, category2: str) -> bool:
    """Convenience function to check if categories are compatible."""
    return get_validator().is_compatible(category1, category2)
