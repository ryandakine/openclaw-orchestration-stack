"""
Date Matcher - Compare event dates with category-specific tolerances.

Module 2.4: Compares dates between prediction market and sportsbook events,
with different tolerance levels for elections (±1 day) vs sports (exact match).
"""

import os
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Union


class DateMatchTolerance(Enum):
    """Tolerance levels for date matching."""
    EXACT = "exact"  # Same day only
    SAME_WEEK = "same_week"  # Within 7 days
    ELECTION = "election"  # ±1 day for elections
    SPORTS = "sports"  # Exact match for sports
    MONTHLY = "monthly"  # Same month
    YEARLY = "yearly"  # Same year


class DateMatcher:
    """Matches dates between events with category-specific tolerances."""
    
    # Default tolerances by category (in days)
    DEFAULT_TOLERANCES: dict[str, int] = {
        "politics": 1,  # Elections: ±1 day
        "sports": 0,  # Sports: exact match
        "football": 0,
        "basketball": 0,
        "baseball": 0,
        "soccer": 0,
        "hockey": 0,
        "mma": 0,
        "tennis": 0,
        "golf": 0,
        "racing": 0,
        "crypto": 1,  # Crypto: ±1 day
        "finance": 1,
        "entertainment": 7,  # Awards: within a week
        "unknown": 1,
    }
    
    def __init__(self) -> None:
        # Load tolerances from environment or use defaults
        self.tolerances: dict[str, int] = {}
        for category, default in self.DEFAULT_TOLERANCES.items():
            env_key = f"OPENCLAW_DATE_TOLERANCE_{category.upper()}"
            env_value = os.getenv(env_key)
            self.tolerances[category] = int(env_value) if env_value else default
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse a date string into datetime object.
        
        Supports multiple formats:
        - ISO: 2024-03-15
        - US: 03/15/2024, 3/15/24
        - European: 15/03/2024 (ambiguous, tries ISO first)
        - Month name: March 15, 2024
        - Year only: 2024
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try ISO format first
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass
        
        # Try US format
        for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # Handle 2-digit years
                if parsed.year < 50:
                    parsed = parsed.replace(year=parsed.year + 2000)
                elif parsed.year < 100:
                    parsed = parsed.replace(year=parsed.year + 1900)
                return parsed
            except ValueError:
                pass
        
        # Try European format (only for unambiguous dates)
        for fmt in ["%d/%m/%Y", "%d-%m-%Y"]:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # Only accept if day > 12 (unambiguous)
                if parsed.day > 12:
                    return parsed
            except ValueError:
                pass
        
        # Try month name formats
        for fmt in [
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%B %Y",
            "%b %Y",
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                pass
        
        # Try year only
        if re.match(r"^\d{4}$", date_str):
            try:
                year = int(date_str)
                return datetime(year, 1, 1)
            except ValueError:
                pass
        
        return None
    
    def match(
        self,
        date1: Union[str, datetime],
        date2: Union[str, datetime],
        category: str = "unknown",
        tolerance_days: Optional[int] = None,
    ) -> float:
        """
        Calculate date match score between two dates.
        
        Args:
            date1: First date (string or datetime)
            date2: Second date (string or datetime)
            category: Event category for tolerance selection
            tolerance_days: Override tolerance (uses category default if None)
        
        Returns:
            Score between 0.0 and 1.0
        """
        # Parse dates if needed
        dt1 = date1 if isinstance(date1, datetime) else self.parse_date(date1)
        dt2 = date2 if isinstance(date2, datetime) else self.parse_date(date2)
        
        if dt1 is None or dt2 is None:
            return 0.0
        
        # Get tolerance
        if tolerance_days is None:
            tolerance_days = self.tolerances.get(category.lower(), 1)
        
        # Calculate difference in days
        diff = abs((dt1 - dt2).days)
        
        # Exact match
        if diff == 0:
            return 1.0
        
        # Within tolerance
        if diff <= tolerance_days:
            # Linear decay from 1.0 to 0.5 at tolerance boundary
            return 1.0 - (0.5 * diff / tolerance_days) if tolerance_days > 0 else 0.5
        
        # Outside tolerance but close
        if diff <= tolerance_days + 1:
            return 0.3
        
        if diff <= tolerance_days + 7:
            return 0.1
        
        return 0.0
    
    def is_match(
        self,
        date1: Union[str, datetime],
        date2: Union[str, datetime],
        category: str = "unknown",
        min_score: float = 0.5,
    ) -> bool:
        """Check if dates match with minimum score."""
        return self.match(date1, date2, category) >= min_score
    
    def get_tolerance(self, category: str) -> int:
        """Get the tolerance days for a category."""
        return self.tolerances.get(category.lower(), 1)
    
    def set_tolerance(self, category: str, days: int) -> None:
        """Set tolerance for a category."""
        self.tolerances[category.lower()] = days
    
    def extract_and_match(
        self,
        text1: str,
        text2: str,
        category: str = "unknown",
    ) -> tuple[float, list[str], list[str]]:
        """
        Extract dates from two texts and compare them.
        
        Returns:
            Tuple of (best_score, dates_from_text1, dates_from_text2)
        """
        dates1 = self.extract_dates(text1)
        dates2 = self.extract_dates(text2)
        
        if not dates1 or not dates2:
            return (0.0, dates1, dates2)
        
        # Find best match
        best_score = 0.0
        for d1 in dates1:
            for d2 in dates2:
                score = self.match(d1, d2, category)
                if score > best_score:
                    best_score = score
        
        return (best_score, dates1, dates2)
    
    def extract_dates(self, text: str) -> list[str]:
        """Extract all date strings from text."""
        dates: list[str] = []
        
        # ISO dates
        iso_pattern = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
        dates.extend(iso_pattern.findall(text))
        
        # US format dates
        us_pattern = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
        dates.extend(us_pattern.findall(text))
        
        # Month name dates
        month_pattern = re.compile(
            r"\b(january|february|march|april|may|june|july|august|"
            r"september|october|november|december|jan|feb|mar|apr|jun|"
            r"jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,\s+(\d{4}))?\b",
            re.IGNORECASE,
        )
        for match in month_pattern.finditer(text):
            month, day, year = match.groups()
            if year:
                dates.append(f"{month} {day}, {year}")
            else:
                dates.append(f"{month} {day}")
        
        # Years
        year_pattern = re.compile(r"\b(20\d{2})\b")
        dates.extend(year_pattern.findall(text))
        
        return dates
    
    def normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize a date string to ISO format."""
        parsed = self.parse_date(date_str)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
        return None
    
    def days_between(
        self,
        date1: Union[str, datetime],
        date2: Union[str, datetime],
    ) -> Optional[int]:
        """Calculate days between two dates."""
        dt1 = date1 if isinstance(date1, datetime) else self.parse_date(date1)
        dt2 = date2 if isinstance(date2, datetime) else self.parse_date(date2)
        
        if dt1 is None or dt2 is None:
            return None
        
        return abs((dt1 - dt2).days)


# Singleton instance
_default_matcher: Optional[DateMatcher] = None


def get_date_matcher() -> DateMatcher:
    """Get the default date matcher instance."""
    global _default_matcher
    if _default_matcher is None:
        _default_matcher = DateMatcher()
    return _default_matcher


def match_dates(
    date1: Union[str, datetime],
    date2: Union[str, datetime],
    category: str = "unknown",
) -> float:
    """Convenience function to match two dates."""
    return get_date_matcher().match(date1, date2, category)


def parse_date(date_str: str) -> Optional[datetime]:
    """Convenience function to parse a date."""
    return get_date_matcher().parse_date(date_str)
