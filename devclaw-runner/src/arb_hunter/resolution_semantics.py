"""
Resolution Semantics - Check that resolution rules match across sources.

Module 2.6: Ensures that "wins election" vs "wins nomination" are correctly
identified as different resolution semantics, preventing false arbitrage signals.
"""

import os
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from rapidfuzz import fuzz


class ResolutionType(Enum):
    """Types of resolution conditions."""
    ELECTION_WIN = "election_win"  # Wins the general election
    NOMINATION_WIN = "nomination_win"  # Wins party nomination
    PRIMARY_WIN = "primary_win"  # Wins a primary/caucus
    POPULAR_VOTE_WIN = "popular_vote_win"  # Wins popular vote (may differ from electoral)
    EVENT_OCCURS = "event_occurs"  # Event happens by date
    PRICE_THRESHOLD = "price_threshold"  # Asset reaches price
    MATCH_WIN = "match_win"  # Team/player wins match
    CHAMPIONSHIP_WIN = "championship_win"  # Wins tournament/championship
    YES_NO = "yes_no"  # Simple binary outcome
    MULTI_OUTCOME = "multi_outcome"  # Multiple possible outcomes
    UNKNOWN = "unknown"


class SemanticDifference(Enum):
    """Types of semantic differences between resolutions."""
    NONE = "none"
    CRITICAL = "critical"  # Completely different outcomes
    SIGNIFICANT = "significant"  # Material difference in resolution
    MINOR = "minor"  # Cosmetic difference only
    TEMPORAL = "temporal"  # Different timing conditions
    SCOPE = "scope"  # Different scope (e.g., primary vs general)


@dataclass
class ResolutionSemantics:
    """Parsed resolution semantics for an event."""
    resolution_type: ResolutionType
    trigger_event: str = ""  # What triggers resolution
    deadline: Optional[str] = None  # Resolution deadline
    conditions: list[str] = None  # Specific conditions
    exclusions: list[str] = None  # Exclusions from resolution
    tie_handling: str = ""  # How ties are handled
    
    def __post_init__(self) -> None:
        if self.conditions is None:
            self.conditions = []
        if self.exclusions is None:
            self.exclusions = []


class ResolutionSemanticsAnalyzer:
    """Analyzes and compares resolution semantics between events."""
    
    # Key phrases that indicate resolution types
    RESOLUTION_PATTERNS: dict[ResolutionType, list[str]] = {
        ResolutionType.ELECTION_WIN: [
            "wins election", "elected", "wins the presidency", "becomes president",
            "wins the general election", "general election winner", "presidential election",
            "wins the race", "elected president", "wins office",
        ],
        ResolutionType.NOMINATION_WIN: [
            "wins nomination", "nominated", "wins the nomination", "party nominee",
            "nomination winner", "wins primary", "primary winner", "wins caucus",
        ],
        ResolutionType.PRIMARY_WIN: [
            "wins primary", "primary winner", "wins caucus", "caucus winner",
            "wins iowa", "wins new hampshire", "state primary",
        ],
        ResolutionType.POPULAR_VOTE_WIN: [
            "wins popular vote", "popular vote winner", "most votes",
            "popular vote plurality", "wins the popular vote",
        ],
        ResolutionType.EVENT_OCCURS: [
            "will happen", "occurs by", "before date", "by end of",
            "takes place", "happens before", "occurs before",
        ],
        ResolutionType.PRICE_THRESHOLD: [
            "above price", "below price", "reaches price", "hits price",
            "price above", "price below", "trades above", "trades below",
        ],
        ResolutionType.MATCH_WIN: [
            "wins the match", "match winner", "to win", "wins the game",
            "game winner", "wins in regulation", "wins outright",
        ],
        ResolutionType.CHAMPIONSHIP_WIN: [
            "wins championship", "championship winner", "wins the title",
            "wins tournament", "tournament winner", "wins the cup",
        ],
        ResolutionType.YES_NO: [
            "yes or no", "will it", "does it", "is it", "binary outcome",
        ],
    }
    
    # Critical semantic differences - these should never be matched
    CRITICAL_DIFFERENCES: list[tuple[set[str], set[str]]] = [
        # Election vs Nomination
        (
            {"wins election", "general election", "elected president"},
            {"wins nomination", "party nominee", "primary winner"},
        ),
        # Popular vote vs Electoral vote
        (
            {"wins popular vote", "popular vote winner"},
            {"wins election", "elected", "electoral college"},
        ),
        # Match vs Championship
        (
            {"wins the match", "match winner", "game winner"},
            {"wins championship", "wins tournament", "wins the title"},
        ),
    ]
    
    def __init__(self) -> None:
        self.min_semantic_score = float(
            os.getenv("OPENCLAW_MIN_SEMANTIC_SCORE", "0.80")
        )
    
    def analyze(self, resolution_text: str, category: str = "") -> ResolutionSemantics:
        """
        Analyze resolution text to extract semantics.
        
        Args:
            resolution_text: Raw resolution rules/description
            category: Event category for context
        
        Returns:
            ResolutionSemantics object with parsed information
        """
        text_lower = resolution_text.lower()
        
        # Determine resolution type
        res_type = self._detect_resolution_type(text_lower)
        
        # Extract trigger event
        trigger = self._extract_trigger(text_lower)
        
        # Extract deadline
        deadline = self._extract_deadline(text_lower)
        
        # Extract conditions
        conditions = self._extract_conditions(text_lower)
        
        # Extract exclusions
        exclusions = self._extract_exclusions(text_lower)
        
        # Extract tie handling
        tie_handling = self._extract_tie_handling(text_lower)
        
        return ResolutionSemantics(
            resolution_type=res_type,
            trigger_event=trigger,
            deadline=deadline,
            conditions=conditions,
            exclusions=exclusions,
            tie_handling=tie_handling,
        )
    
    def compare(
        self,
        resolution1: str,
        resolution2: str,
    ) -> tuple[float, SemanticDifference, str]:
        """
        Compare two resolution texts for semantic similarity.
        
        Args:
            resolution1: First resolution text
            resolution2: Second resolution text
        
        Returns:
            Tuple of (score, difference_type, explanation)
        """
        sem1 = self.analyze(resolution1)
        sem2 = self.analyze(resolution2)
        
        # Check for critical differences first
        critical = self._check_critical_difference(resolution1, resolution2)
        if critical:
            return (0.0, SemanticDifference.CRITICAL, critical)
        
        # Compare resolution types
        type_score = self._compare_resolution_types(
            sem1.resolution_type, sem2.resolution_type
        )
        
        # Compare trigger events
        trigger_score = self._compare_triggers(sem1.trigger_event, sem2.trigger_event)
        
        # Compare deadlines
        deadline_score = self._compare_deadlines(sem1.deadline, sem2.deadline)
        
        # Compare conditions
        condition_score = self._compare_conditions(sem1.conditions, sem2.conditions)
        
        # Calculate weighted score
        weights = {
            "type": 0.35,
            "trigger": 0.25,
            "deadline": 0.20,
            "conditions": 0.20,
        }
        
        final_score = (
            type_score * weights["type"] +
            trigger_score * weights["trigger"] +
            deadline_score * weights["deadline"] +
            condition_score * weights["conditions"]
        )
        
        # Determine difference type
        diff_type, explanation = self._classify_difference(
            final_score, sem1, sem2, resolution1, resolution2
        )
        
        return (final_score, diff_type, explanation)
    
    def is_compatible(
        self,
        resolution1: str,
        resolution2: str,
        min_score: Optional[float] = None,
    ) -> bool:
        """Quick check if resolutions are semantically compatible."""
        score, diff_type, _ = self.compare(resolution1, resolution2)
        threshold = min_score if min_score is not None else self.min_semantic_score
        
        if diff_type == SemanticDifference.CRITICAL:
            return False
        
        return score >= threshold
    
    def _detect_resolution_type(self, text: str) -> ResolutionType:
        """Detect the resolution type from text."""
        scores: dict[ResolutionType, int] = {}
        
        for res_type, patterns in self.RESOLUTION_PATTERNS.items():
            score = sum(1 for pattern in patterns if pattern in text)
            if score > 0:
                scores[res_type] = score
        
        if scores:
            return max(scores, key=scores.get)  # type: ignore
        
        return ResolutionType.UNKNOWN
    
    def _extract_trigger(self, text: str) -> str:
        """Extract the trigger event from resolution text."""
        # Look for "this market resolves to YES if..." patterns
        patterns = [
            r"resolves to yes if (.+?)(?:\.|$|when)",
            r"resolves yes if (.+?)(?:\.|$|when)",
            r"market resolves when (.+?)(?:\.|$)",
            r"resolves based on (.+?)(?:\.|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""
    
    def _extract_deadline(self, text: str) -> Optional[str]:
        """Extract resolution deadline from text."""
        # Look for date patterns
        date_patterns = [
            r"by\s+(january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}",
            r"by\s+(\d{4}-\d{2}-\d{2})",
            r"before\s+(january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\s+\d{1,2}",
            r"end of\s+(\d{4})",
            r"(\d{4})\s+deadline",
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_conditions(self, text: str) -> list[str]:
        """Extract specific resolution conditions."""
        conditions: list[str] = []
        
        # Look for conditional phrases
        condition_patterns = [
            r"if\s+(.+?)(?:,|then|and|or|$)",
            r"provided that\s+(.+?)(?:,|and|or|$)",
            r"assuming\s+(.+?)(?:,|and|or|$)",
        ]
        
        for pattern in condition_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                condition = match.group(1).strip()
                if len(condition) > 5:
                    conditions.append(condition)
        
        return conditions
    
    def _extract_exclusions(self, text: str) -> list[str]:
        """Extract exclusions from resolution text."""
        exclusions: list[str] = []
        
        exclusion_patterns = [
            r"excluding\s+(.+?)(?:,|and|or|$)",
            r"does not include\s+(.+?)(?:,|and|or|$)",
            r"except\s+(.+?)(?:,|and|or|$)",
        ]
        
        for pattern in exclusion_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                exclusion = match.group(1).strip()
                if len(exclusion) > 3:
                    exclusions.append(exclusion)
        
        return exclusions
    
    def _extract_tie_handling(self, text: str) -> str:
        """Extract how ties are handled."""
        tie_patterns = [
            r"tie\s+(?:will be|is)\s+(.+?)(?:\.|$)",
            r"in\s+(?:the\s+)?event\s+of\s+a\s+tie\s+(.+?)(?:\.|$)",
            r"tied\s+(.+?)(?:\.|$)",
        ]
        
        for pattern in tie_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""
    
    def _check_critical_difference(self, text1: str, text2: str) -> str:
        """Check for critical semantic differences that make matching impossible."""
        t1_lower = text1.lower()
        t2_lower = text2.lower()
        
        for set1, set2 in self.CRITICAL_DIFFERENCES:
            in1 = any(phrase in t1_lower for phrase in set1)
            in2 = any(phrase in t2_lower for phrase in set2)
            
            if in1 and in2:
                return f"Critical difference: {set1} vs {set2}"
            
            # Check reverse too
            in1_rev = any(phrase in t1_lower for phrase in set2)
            in2_rev = any(phrase in t2_lower for phrase in set1)
            
            if in1_rev and in2_rev:
                return f"Critical difference: {set2} vs {set1}"
        
        return ""
    
    def _compare_resolution_types(
        self,
        type1: ResolutionType,
        type2: ResolutionType,
    ) -> float:
        """Compare two resolution types."""
        if type1 == type2:
            return 1.0
        
        # Related types
        related = {
            ResolutionType.ELECTION_WIN: {ResolutionType.POPULAR_VOTE_WIN},
            ResolutionType.NOMINATION_WIN: {ResolutionType.PRIMARY_WIN},
            ResolutionType.MATCH_WIN: {ResolutionType.CHAMPIONSHIP_WIN},
        }
        
        if type2 in related.get(type1, set()):
            return 0.5
        if type1 in related.get(type2, set()):
            return 0.5
        
        return 0.0
    
    def _compare_triggers(self, trigger1: str, trigger2: str) -> float:
        """Compare trigger events using fuzzy matching."""
        if not trigger1 or not trigger2:
            return 0.5  # Neutral if missing
        
        return fuzz.ratio(trigger1.lower(), trigger2.lower()) / 100.0
    
    def _compare_deadlines(
        self,
        deadline1: Optional[str],
        deadline2: Optional[str],
    ) -> float:
        """Compare resolution deadlines."""
        if deadline1 is None and deadline2 is None:
            return 1.0
        
        if deadline1 is None or deadline2 is None:
            return 0.5  # One has deadline, other doesn't
        
        # Fuzzy match deadline strings
        return fuzz.ratio(deadline1.lower(), deadline2.lower()) / 100.0
    
    def _compare_conditions(self, conds1: list[str], conds2: list[str]) -> float:
        """Compare resolution conditions."""
        if not conds1 and not conds2:
            return 1.0
        
        if not conds1 or not conds2:
            return 0.5
        
        # Compare condition lists
        matches = 0
        for c1 in conds1:
            for c2 in conds2:
                if fuzz.ratio(c1.lower(), c2.lower()) > 80:
                    matches += 1
                    break
        
        max_conds = max(len(conds1), len(conds2))
        return matches / max_conds if max_conds > 0 else 0.0
    
    def _classify_difference(
        self,
        score: float,
        sem1: ResolutionSemantics,
        sem2: ResolutionSemantics,
        text1: str,
        text2: str,
    ) -> tuple[SemanticDifference, str]:
        """Classify the type of difference between resolutions."""
        if score >= 0.9:
            return (SemanticDifference.NONE, "Resolutions are semantically equivalent")
        
        if score <= 0.3:
            return (SemanticDifference.CRITICAL, "Fundamentally different resolutions")
        
        # Check for temporal differences
        if sem1.deadline != sem2.deadline:
            return (SemanticDifference.TEMPORAL, "Different resolution deadlines")
        
        # Check for scope differences
        if sem1.resolution_type != sem2.resolution_type:
            if score < 0.7:
                return (SemanticDifference.SCOPE, "Different resolution scope")
        
        if score < 0.7:
            return (SemanticDifference.SIGNIFICANT, "Material difference in conditions")
        
        return (SemanticDifference.MINOR, "Minor wording differences")


# Singleton instance
_default_analyzer: Optional[ResolutionSemanticsAnalyzer] = None


def get_analyzer() -> ResolutionSemanticsAnalyzer:
    """Get the default resolution semantics analyzer."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = ResolutionSemanticsAnalyzer()
    return _default_analyzer


def compare_resolutions(resolution1: str, resolution2: str) -> tuple[float, str]:
    """
    Convenience function to compare two resolutions.
    
    Returns:
        Tuple of (score, explanation)
    """
    score, diff_type, explanation = get_analyzer().compare(resolution1, resolution2)
    return (score, explanation)


def are_resolutions_compatible(resolution1: str, resolution2: str) -> bool:
    """Convenience function to check if resolutions are compatible."""
    return get_analyzer().is_compatible(resolution1, resolution2)
