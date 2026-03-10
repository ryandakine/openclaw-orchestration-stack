"""
Outcome Mapper - Map outcomes between prediction markets and sportsbooks.

Module 2.8: Maps YES/NO outcomes across sources, handling:
- Polymarket YES ↔ sportsbook implied NOT-YES
- Direct mappings for named outcomes
- Inverse mappings for complementary bets
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from rapidfuzz import fuzz


class MappingDirection(Enum):
    """Direction of outcome mapping."""
    DIRECT = "direct"  # Same outcome
    INVERSE = "inverse"  # Complementary outcome
    IMPLIED = "implied"  # Derived from multiple outcomes
    UNMAPPED = "unmapped"  # Cannot map


class OutcomeType(Enum):
    """Standardized outcome types."""
    YES = "yes"
    NO = "no"
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"
    OVER = "over"
    UNDER = "under"
    HOME_WIN = "home_win"
    AWAY_WIN = "away_win"
    UNKNOWN = "unknown"


@dataclass
class OutcomeMapping:
    """Result of outcome mapping."""
    source_outcome: str
    target_outcome: str
    direction: MappingDirection
    confidence: float = 0.0
    explanation: str = ""
    implied_probability_adjustment: float = 0.0  # For implied mappings


class OutcomeNormalizer:
    """Normalizes outcome strings for consistent comparison."""
    
    # Outcome aliases
    OUTCOME_ALIASES: dict[str, list[str]] = {
        "yes": ["yes", "y", "true", "1", "over", " bullish"],
        "no": ["no", "n", "false", "0", "under", "bearish"],
        "win": ["win", "wins", "winner", "victory", "to win", "moneyline"],
        "loss": ["loss", "lose", "loser", "defeat"],
        "draw": ["draw", "tie", "push", "no result"],
        "over": ["over", "o", "above"],
        "under": ["under", "u", "below"],
    }
    
    def normalize(self, outcome: str) -> str:
        """Normalize an outcome string."""
        if not outcome:
            return ""
        
        outcome_lower = outcome.lower().strip()
        
        # Remove market type suffixes
        suffixes = [
            r"\s*\(\s*regulation\s*\)",
            r"\s*[-–—]\s*moneyline",
            r"\s*[-–—]\s*to win",
            r"\s*[-–—]\s*spread",
            r"\s*[-–—]\s*total",
        ]
        
        for suffix in suffixes:
            outcome_lower = re.sub(suffix, "", outcome_lower)
        
        outcome_lower = outcome_lower.strip()
        
        # Check aliases
        for standard, aliases in self.OUTCOME_ALIASES.items():
            if outcome_lower in aliases:
                return standard
        
        return outcome_lower
    
    def is_yes_no_market(self, outcomes: list[str]) -> bool:
        """Check if outcomes represent a YES/NO market."""
        normalized = [self.normalize(o) for o in outcomes]
        normalized_set = set(normalized)
        
        yes_aliases = set(self.OUTCOME_ALIASES["yes"])
        no_aliases = set(self.OUTCOME_ALIASES["no"])
        
        has_yes = bool(normalized_set & yes_aliases)
        has_no = bool(normalized_set & no_aliases)
        
        return has_yes and has_no


class OutcomeMapper:
    """Maps outcomes between prediction markets and sportsbooks."""
    
    def __init__(self) -> None:
        self.normalizer = OutcomeNormalizer()
        self.min_confidence = float(os.getenv("OPENCLAW_OUTCOME_MIN_CONFIDENCE", "0.80"))
    
    def map_outcomes(
        self,
        pm_outcome: str,
        sb_outcome: str,
        pm_title: str = "",
        sb_title: str = "",
    ) -> OutcomeMapping:
        """
        Map a prediction market outcome to a sportsbook outcome.
        
        Args:
            pm_outcome: Prediction market outcome (YES/NO or named)
            sb_outcome: Sportsbook outcome description
            pm_title: Prediction market title (for context)
            sb_title: Sportsbook event title (for context)
        
        Returns:
            OutcomeMapping with mapping details
        """
        norm_pm = self.normalizer.normalize(pm_outcome)
        norm_sb = self.normalizer.normalize(sb_outcome)
        
        # Direct match
        if norm_pm == norm_sb:
            return OutcomeMapping(
                source_outcome=pm_outcome,
                target_outcome=sb_outcome,
                direction=MappingDirection.DIRECT,
                confidence=1.0,
                explanation=f"Direct match: {norm_pm} = {norm_sb}",
            )
        
        # YES/NO market mapping
        if norm_pm in ("yes", "no"):
            return self._map_yes_no(
                norm_pm, sb_outcome, pm_title, sb_title
            )
        
        # Named outcome mapping (e.g., team names)
        named_mapping = self._map_named_outcome(
            pm_outcome, sb_outcome, pm_title, sb_title
        )
        if named_mapping.confidence >= self.min_confidence:
            return named_mapping
        
        # Try fuzzy matching
        fuzzy_score = fuzz.ratio(norm_pm, norm_sb) / 100.0
        if fuzzy_score >= self.min_confidence:
            return OutcomeMapping(
                source_outcome=pm_outcome,
                target_outcome=sb_outcome,
                direction=MappingDirection.DIRECT,
                confidence=fuzzy_score,
                explanation=f"Fuzzy match: {fuzzy_score:.2f} similarity",
            )
        
        # Check for inverse relationship
        inverse_mapping = self._check_inverse_mapping(
            pm_outcome, sb_outcome, pm_title, sb_title
        )
        if inverse_mapping.confidence >= self.min_confidence:
            return inverse_mapping
        
        # Unmapped
        return OutcomeMapping(
            source_outcome=pm_outcome,
            target_outcome=sb_outcome,
            direction=MappingDirection.UNMAPPED,
            confidence=fuzzy_score,
            explanation=f"Cannot map: insufficient similarity ({fuzzy_score:.2f})",
        )
    
    def _map_yes_no(
        self,
        pm_outcome: str,
        sb_outcome: str,
        pm_title: str,
        sb_title: str,
    ) -> OutcomeMapping:
        """Map YES/NO outcome to sportsbook outcome."""
        norm_sb = self.normalizer.normalize(sb_outcome)
        
        # YES mappings
        if pm_outcome == "yes":
            # Sportsbook says "Trump wins" → maps to Polymarket YES
            if any(keyword in sb_title.lower() for keyword in ["wins", "win", "victory"]):
                if fuzz.partial_ratio(pm_title.lower(), sb_title.lower()) > 70:
                    return OutcomeMapping(
                        source_outcome="YES",
                        target_outcome=sb_outcome,
                        direction=MappingDirection.DIRECT,
                        confidence=0.9,
                        explanation="YES matches 'wins' outcome",
                    )
            
            # Check if sportsbook outcome is the positive case
            if norm_sb in ("win", "wins", "winner", "over"):
                return OutcomeMapping(
                    source_outcome="YES",
                    target_outcome=sb_outcome,
                    direction=MappingDirection.DIRECT,
                    confidence=0.95,
                    explanation="YES = win outcome",
                )
            
            # Check for inverse: YES = NOT the negative outcome
            if norm_sb in ("loss", "lose", "under", "no"):
                return OutcomeMapping(
                    source_outcome="YES",
                    target_outcome=sb_outcome,
                    direction=MappingDirection.INVERSE,
                    confidence=0.85,
                    explanation="YES = NOT (loss/under outcome)",
                    implied_probability_adjustment=1.0,  # Will need probability inversion
                )
        
        # NO mappings
        if pm_outcome == "no":
            # NO is inverse of YES
            if norm_sb in ("win", "wins", "winner", "over", "yes"):
                return OutcomeMapping(
                    source_outcome="NO",
                    target_outcome=sb_outcome,
                    direction=MappingDirection.INVERSE,
                    confidence=0.9,
                    explanation="NO = NOT (win outcome)",
                    implied_probability_adjustment=1.0,
                )
            
            # NO matches loss/negative outcomes
            if norm_sb in ("loss", "lose", "under", "no"):
                return OutcomeMapping(
                    source_outcome="NO",
                    target_outcome=sb_outcome,
                    direction=MappingDirection.DIRECT,
                    confidence=0.95,
                    explanation="NO = loss/under outcome",
                )
        
        return OutcomeMapping(
            source_outcome=pm_outcome,
            target_outcome=sb_outcome,
            direction=MappingDirection.UNMAPPED,
            confidence=0.5,
            explanation="Unclear YES/NO mapping",
        )
    
    def _map_named_outcome(
        self,
        pm_outcome: str,
        sb_outcome: str,
        pm_title: str,
        sb_title: str,
    ) -> OutcomeMapping:
        """Map named outcomes (e.g., team names)."""
        # Extract entities from titles and compare to outcomes
        pm_entities = self._extract_entities(pm_title)
        sb_entities = self._extract_entities(sb_title)
        
        # Check if PM outcome matches SB outcome directly
        pm_outcome_lower = pm_outcome.lower()
        sb_outcome_lower = sb_outcome.lower()
        
        # Direct substring match
        if pm_outcome_lower in sb_outcome_lower or sb_outcome_lower in pm_outcome_lower:
            return OutcomeMapping(
                source_outcome=pm_outcome,
                target_outcome=sb_outcome,
                direction=MappingDirection.DIRECT,
                confidence=0.9,
                explanation="Named outcome direct match",
            )
        
        # Fuzzy match on outcomes
        fuzzy_score = fuzz.token_set_ratio(pm_outcome_lower, sb_outcome_lower) / 100.0
        
        return OutcomeMapping(
            source_outcome=pm_outcome,
            target_outcome=sb_outcome,
            direction=MappingDirection.DIRECT if fuzzy_score > 0.8 else MappingDirection.UNMAPPED,
            confidence=fuzzy_score,
            explanation="Named outcome fuzzy match" if fuzzy_score > 0.8 else "Weak named outcome match",
        )
    
    def _check_inverse_mapping(
        self,
        pm_outcome: str,
        sb_outcome: str,
        pm_title: str,
        sb_title: str,
    ) -> OutcomeMapping:
        """Check if outcomes have an inverse relationship."""
        norm_pm = self.normalizer.normalize(pm_outcome)
        norm_sb = self.normalizer.normalize(sb_outcome)
        
        # Known inverse pairs
        inverse_pairs = [
            ("win", "loss"),
            ("over", "under"),
            ("yes", "no"),
            ("home_win", "away_win"),
        ]
        
        for pos, neg in inverse_pairs:
            if norm_pm == pos and norm_sb == neg:
                return OutcomeMapping(
                    source_outcome=pm_outcome,
                    target_outcome=sb_outcome,
                    direction=MappingDirection.INVERSE,
                    confidence=0.9,
                    explanation=f"Inverse: {pos} vs {neg}",
                    implied_probability_adjustment=1.0,
                )
            if norm_pm == neg and norm_sb == pos:
                return OutcomeMapping(
                    source_outcome=pm_outcome,
                    target_outcome=sb_outcome,
                    direction=MappingDirection.INVERSE,
                    confidence=0.9,
                    explanation=f"Inverse: {neg} vs {pos}",
                    implied_probability_adjustment=1.0,
                )
        
        return OutcomeMapping(
            source_outcome=pm_outcome,
            target_outcome=sb_outcome,
            direction=MappingDirection.UNMAPPED,
            confidence=0.0,
            explanation="No inverse relationship detected",
        )
    
    def _extract_entities(self, text: str) -> list[str]:
        """Extract potential entities (names, teams) from text."""
        # Simple entity extraction - split on common delimiters
        delimiters = r"[\s\-–—_()\[\]]+"
        parts = re.split(delimiters, text.lower())
        
        # Filter for likely entities (capitalized words in original, length > 2)
        entities = [p for p in parts if len(p) > 2]
        
        return entities
    
    def calculate_implied_probability(
        self,
        outcome_mapping: OutcomeMapping,
        source_probability: float,
    ) -> float:
        """
        Calculate implied probability for target outcome.
        
        Args:
            outcome_mapping: The mapping result
            source_probability: Probability of source outcome (0-1)
        
        Returns:
            Implied probability of target outcome
        """
        if outcome_mapping.direction == MappingDirection.DIRECT:
            return source_probability
        
        if outcome_mapping.direction == MappingDirection.INVERSE:
            # Inverse probability: P(NOT A) = 1 - P(A)
            return 1.0 - source_probability
        
        if outcome_mapping.direction == MappingDirection.IMPLIED:
            # Implied mappings may have specific adjustments
            return source_probability + outcome_mapping.implied_probability_adjustment
        
        return source_probability
    
    def get_all_mappings(
        self,
        pm_outcomes: list[str],
        sb_outcomes: list[str],
        pm_title: str = "",
        sb_title: str = "",
    ) -> list[OutcomeMapping]:
        """
        Get all possible mappings between two sets of outcomes.
        
        Returns:
            List of OutcomeMapping objects
        """
        mappings: list[OutcomeMapping] = []
        
        for pm_outcome in pm_outcomes:
            best_mapping: Optional[OutcomeMapping] = None
            
            for sb_outcome in sb_outcomes:
                mapping = self.map_outcomes(pm_outcome, sb_outcome, pm_title, sb_title)
                
                if best_mapping is None or mapping.confidence > best_mapping.confidence:
                    best_mapping = mapping
            
            if best_mapping:
                mappings.append(best_mapping)
        
        return mappings


# Singleton instance
_default_mapper: Optional[OutcomeMapper] = None


def get_mapper() -> OutcomeMapper:
    """Get the default outcome mapper instance."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = OutcomeMapper()
    return _default_mapper


def map_outcome(
    pm_outcome: str,
    sb_outcome: str,
    pm_title: str = "",
    sb_title: str = "",
) -> OutcomeMapping:
    """Convenience function to map an outcome."""
    return get_mapper().map_outcomes(pm_outcome, sb_outcome, pm_title, sb_title)


def is_inverse_mapping(mapping: OutcomeMapping) -> bool:
    """Check if a mapping represents an inverse relationship."""
    return mapping.direction == MappingDirection.INVERSE
