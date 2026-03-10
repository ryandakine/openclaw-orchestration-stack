"""
Entity Extractor - Extract named entities from event titles and descriptions.

Module 2.3: Uses regex patterns and rule-based extraction to identify
candidates, teams, dates, locations, and other key entities.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from match_result_schema import EntitySet


# Environment configuration
ENTITY_EXTRACTION_STRICT = os.getenv("OPENCLAW_ENTITY_STRICT_MODE", "false").lower() == "true"


@dataclass
class ExtractionContext:
    """Context hints for entity extraction."""
    category: str = ""  # "politics", "sports", "crypto", etc.
    source: str = ""  # "polymarket", "draftkings", etc.
    event_type: str = ""  # "election", "match", "award", etc.


class EntityExtractor:
    """Extracts entities from event titles and descriptions."""
    
    # Political candidates and figures (common patterns)
    POLITICAL_TITLES = frozenset({
        "president", "vice president", "senator", "governor", "mayor",
        "representative", "rep", "sec", "secretary", "prime minister",
        "pm", "chancellor", "leader", "chairman", "chairwoman",
    })
    
    # Known political figures for quick matching (last names)
    KNOWN_POLITICIANS = frozenset({
        "trump", "biden", "harris", "vance", "walz", "rfk", "kennedy",
        "newsom", "desantis", "haley", "christie", "pence", "buttigieg",
        "sanders", "warren", "cruz", "rubio", "paul", "mcconnell",
        "schumer", "pelosi", "johnson", "jeffries", "mcCarthy",
    })
    
    # Sports leagues for context
    SPORTS_LEAGUES = {
        "nfl": "football",
        "nba": "basketball",
        "mlb": "baseball",
        "nhl": "hockey",
        "mls": "soccer",
        "premier league": "soccer",
        "la liga": "soccer",
        "bundesliga": "soccer",
        "serie a": "soccer",
        "ligue 1": "soccer",
        "uefa": "soccer",
        "champions league": "soccer",
        "world cup": "soccer",
        "olympics": "multi",
        "ufc": "mma",
        "wwe": "wrestling",
        "atp": "tennis",
        "wta": "tennis",
        "pga": "golf",
        "formula 1": "racing",
        "f1": "racing",
        "nascar": "racing",
    }
    
    # Team name patterns
    TEAM_NAME_PATTERN = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:fc|united|city|fc|sc|ac|real|")
    
    def __init__(self) -> None:
        # Date patterns
        self.date_patterns = [
            # ISO format: 2024-03-15
            re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
            # US format: 03/15/2024 or 3/15/24
            re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),
            # Month name: March 15, 2024 or Mar 15
            re.compile(
                r"\b(january|february|march|april|may|june|july|august|"
                r"september|october|november|december|jan|feb|mar|apr|jun|"
                r"jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,\s+(\d{4}))?\b",
                re.IGNORECASE,
            ),
            # Year only: 2024
            re.compile(r"\b(20\d{2})\b"),
        ]
        
        # Person name patterns (First Last)
        self.name_pattern = re.compile(
            r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b"
        )
        
        # Single name (capitalized, likely a last name)
        self.last_name_pattern = re.compile(r"\b([A-Z][a-z]{2,})\b")
        
        # Location patterns
        self.location_patterns = [
            re.compile(r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
            re.compile(r"\bat\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
        ]
        
        # Organization patterns
        self.org_patterns = [
            re.compile(r"\b([A-Z]{2,})\b"),  # Acronyms
            re.compile(r"\b([A-Z][a-z]+\s+(?:Inc|Corp|LLC|Ltd|Company|Association))\b"),
        ]
    
    def extract(
        self,
        title: str,
        description: str = "",
        context: Optional[ExtractionContext] = None,
    ) -> EntitySet:
        """
        Extract all entities from event title and description.
        
        Args:
            title: Event title
            description: Optional event description
            context: Optional context hints
        
        Returns:
            EntitySet containing all extracted entities
        """
        full_text = f"{title} {description}".strip()
        
        ctx = context or ExtractionContext()
        
        # Determine category if not provided
        if not ctx.category:
            ctx.category = self._detect_category(full_text)
        
        candidates: set[str] = set()
        teams: set[str] = set()
        players: set[str] = set()
        dates: set[str] = set()
        locations: set[str] = set()
        organizations: set[str] = set()
        
        # Category-specific extraction
        if ctx.category == "politics":
            candidates = self._extract_political_candidates(full_text)
        elif ctx.category in ("sports", "football", "basketball", "baseball", "soccer"):
            teams, players = self._extract_sports_entities(full_text)
        else:
            # Generic extraction
            candidates = self._extract_persons(full_text)
        
        # Common extractions for all categories
        dates = self._extract_dates(full_text)
        locations = self._extract_locations(full_text)
        organizations = self._extract_organizations(full_text)
        
        return EntitySet(
            candidates=frozenset(candidates),
            teams=frozenset(teams),
            players=frozenset(players),
            dates=frozenset(dates),
            locations=frozenset(locations),
            organizations=frozenset(organizations),
        )
    
    def _detect_category(self, text: str) -> str:
        """Detect event category from text."""
        text_lower = text.lower()
        
        # Check for sports leagues
        for league, sport in self.SPORTS_LEAGUES.items():
            if league in text_lower:
                return sport
        
        # Check for sports indicators
        sports_indicators = ["vs", "versus", "@", "team", "game", "match", "win"]
        if any(ind in text_lower for ind in sports_indicators):
            return "sports"
        
        # Check for politics indicators
        politics_indicators = [
            "election", "president", "vote", "nomination", "candidate",
            "senate", "house", "congress", "governor", "mayor",
        ]
        if any(ind in text_lower for ind in politics_indicators):
            return "politics"
        
        # Check for crypto
        crypto_indicators = ["bitcoin", "ethereum", "crypto", "btc", "eth", "token"]
        if any(ind in text_lower for ind in crypto_indicators):
            return "crypto"
        
        return "unknown"
    
    def _extract_political_candidates(self, text: str) -> set[str]:
        """Extract political candidate names from text."""
        candidates: set[str] = set()
        text_lower = text.lower()
        
        # Check for known politicians
        for pol in self.KNOWN_POLITICIANS:
            if pol in text_lower:
                candidates.add(pol.title())
        
        # Extract full names
        for match in self.name_pattern.finditer(text):
            first, last = match.groups()
            full_name = f"{first} {last}"
            
            # Filter out common false positives
            if self._is_likely_name(first, last):
                candidates.add(full_name)
                candidates.add(last)
        
        return candidates
    
    def _extract_sports_entities(self, text: str) -> tuple[set[str], set[str]]:
        """Extract team and player names from sports events."""
        teams: set[str] = set()
        players: set[str] = set()
        
        # Common team vs team pattern: "Team A vs Team B"
        vs_patterns = [
            re.compile(r"\b([A-Z][a-zA-Z\s]+?)\s+(?:vs\.?|versus)\s+([A-Z][a-zA-Z\s]+?)\b"),
            re.compile(r"\b([A-Z][a-zA-Z\s]+?)\s+@\s+([A-Z][a-zA-Z\s]+?)\b"),
        ]
        
        for pattern in vs_patterns:
            for match in pattern.finditer(text):
                team1 = match.group(1).strip()
                team2 = match.group(2).strip()
                
                # Clean up team names
                team1 = self._clean_team_name(team1)
                team2 = self._clean_team_name(team2)
                
                if team1:
                    teams.add(team1)
                if team2:
                    teams.add(team2)
        
        # Extract player names (less reliable, needs more context)
        for match in self.name_pattern.finditer(text):
            first, last = match.groups()
            if self._is_likely_name(first, last):
                players.add(f"{first} {last}")
        
        return teams, players
    
    def _extract_persons(self, text: str) -> set[str]:
        """Generic person name extraction."""
        persons: set[str] = set()
        
        for match in self.name_pattern.finditer(text):
            first, last = match.groups()
            if self._is_likely_name(first, last):
                persons.add(f"{first} {last}")
                persons.add(last)
        
        return persons
    
    def _extract_dates(self, text: str) -> set[str]:
        """Extract dates from text and normalize to ISO format."""
        dates: set[str] = set()
        
        # ISO dates
        for match in self.date_patterns[0].finditer(text):
            dates.add(match.group(1))
        
        # US format dates
        for match in self.date_patterns[1].finditer(text):
            try:
                parts = match.group(1).split("/")
                if len(parts) == 3:
                    month, day, year = parts
                    if len(year) == 2:
                        year = "20" + year
                    date_obj = datetime(int(year), int(month), int(day))
                    dates.add(date_obj.strftime("%Y-%m-%d"))
            except (ValueError, IndexError):
                pass
        
        # Month name dates
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        
        for match in self.date_patterns[2].finditer(text):
            try:
                month_str = match.group(1).lower()
                day = int(match.group(2))
                year_str = match.group(3)
                
                month = month_map.get(month_str)
                if month:
                    year = int(year_str) if year_str else datetime.now().year
                    date_obj = datetime(year, month, day)
                    dates.add(date_obj.strftime("%Y-%m-%d"))
            except (ValueError, IndexError):
                pass
        
        # Year only
        for match in self.date_patterns[3].finditer(text):
            dates.add(match.group(1))
        
        return dates
    
    def _extract_locations(self, text: str) -> set[str]:
        """Extract location mentions from text."""
        locations: set[str] = set()
        
        for pattern in self.location_patterns:
            for match in pattern.finditer(text):
                location = match.group(1).strip()
                if len(location) > 2:
                    locations.add(location)
        
        return locations
    
    def _extract_organizations(self, text: str) -> set[str]:
        """Extract organization names and acronyms."""
        orgs: set[str] = set()
        
        for pattern in self.org_patterns:
            for match in pattern.finditer(text):
                org = match.group(1).strip()
                if len(org) > 1:
                    orgs.add(org)
        
        return orgs
    
    def _is_likely_name(self, first: str, last: str) -> bool:
        """Check if first/last combination is likely a real name."""
        # Filter out common false positives
        not_names = frozenset({
            "the", "for", "will", "can", "may", "new", "old", "big", "top",
            "win", "won", "los", "san", "las", "los", "van", "den",
        })
        
        if first.lower() in not_names or last.lower() in not_names:
            return False
        
        # Filter out single character "names"
        if len(first) < 2 or len(last) < 2:
            return False
        
        return True
    
    def _clean_team_name(self, name: str) -> str:
        """Clean and normalize a team name."""
        # Remove common suffixes
        suffixes = [
            "fc", "united", "city", "sc", "ac", "real", "cf", "afc",
            "-", "to win", "moneyline",
        ]
        
        name_lower = name.lower()
        for suffix in suffixes:
            if name_lower.endswith(" " + suffix):
                name = name[: -(len(suffix) + 1)].strip()
                name_lower = name.lower()
        
        return name.strip()


# Singleton instance
_default_extractor: Optional[EntityExtractor] = None


def get_extractor() -> EntityExtractor:
    """Get the default entity extractor instance."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = EntityExtractor()
    return _default_extractor


def extract_entities(
    title: str,
    description: str = "",
    category: str = "",
    source: str = "",
) -> EntitySet:
    """Convenience function to extract entities."""
    context = ExtractionContext(category=category, source=source)
    return get_extractor().extract(title, description, context)
