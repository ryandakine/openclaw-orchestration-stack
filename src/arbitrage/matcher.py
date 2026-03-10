"""
Event matching logic for arbitrage detection.

This module provides functions for matching equivalent events across different
sportsbooks and prediction markets using fuzzy string matching and entity extraction.
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import List, Tuple, Optional, Set

from .models import (
    NormalizedMarket,
    MatchedEvent,
    MatchResult,
    MarketType,
    MarketOutcome,
)


def normalize_team_name(name: str) -> str:
    """
    Normalize a team/player name for matching.
    
    This function:
    - Converts to lowercase
    - Removes common suffixes (FC, United, etc.)
    - Removes punctuation
    - Standardizes common abbreviations
    
    Args:
        name: Raw team/player name
        
    Returns:
        Normalized name
    """
    # Convert to lowercase
    normalized = name.lower().strip()
    
    # Standardize common abbreviations (do this first, before removing punctuation)
    replacements = {
        r'\bman united\b': 'manchester united',
        r'\bman utd\b': 'manchester united',
        r'\bman city\b': 'manchester city',
        r'\butd\b': 'united',
        r'\bny\b': 'new york',
        r'\bla\b': 'los angeles',
        r'\blv\b': 'las vegas',
        r'\bsf\b': 'san francisco',
        r'\bkc\b': 'kansas city',
        r'\btb\b': 'tampa bay',
        r'\bgb\b': 'green bay',
    }
    
    for old, new in replacements.items():
        normalized = re.sub(old, new, normalized)
    
    # Remove common sports suffixes (word boundaries)
    # Note: We keep 'united' and 'city' as they're integral to team names
    suffixes = [
        r'\bfc\b', r'\bcf\b', r'\btown\b', r'\bsc\b', 
        r'\bsporting\b', r'\breal\b', r'\bas\b', r'\bclub\b',
    ]
    for suffix in suffixes:
        normalized = re.sub(suffix, '', normalized)
    
    # Remove punctuation and extra whitespace
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized.strip()


def extract_entities(title: str) -> Set[str]:
    """
    Extract team/player names from an event title.
    
    Args:
        title: Event title (e.g., "Lakers vs Warriors")
        
    Returns:
        Set of normalized entity names
    """
    # Common separators
    separators = [' vs ', ' vs. ', ' v ', ' @ ', ' at ', ' - ', ' – ', ' — ']
    
    temp_title = title.lower()
    
    # Replace various separators with a standard one
    for sep in separators:
        temp_title = temp_title.replace(sep, ' | ')
    
    # Common words to remove (expanded list)
    words_to_remove = [
        'will', 'win', 'the', 'at', 'on', 'in', 'score',
        'points', 'defeat', 'election', 'presidential', '2024', '2025', '2026',
        'over', 'under', 'yes', 'no', 'true', 'false',
    ]
    
    # Remove common words first
    for word in words_to_remove:
        temp_title = re.sub(rf'\b{re.escape(word)}\b', '', temp_title)
    
    # Remove standalone punctuation
    temp_title = re.sub(r'[?]', '', temp_title)
    
    # Remove numbers (like 30+ from "30+ points")
    temp_title = re.sub(r'\b\d+\+?\b', '', temp_title)
    
    # Now split by separators
    parts = temp_title.split(' | ')
    
    entities = []
    for part in parts:
        # Clean up each entity
        entity = part.strip()
        entity = normalize_team_name(entity)
        entity = entity.strip()
        
        # If entity contains multiple words and no separator was found,
        # it might be multiple entities joined together
        # Try to split by common patterns
        if ' ' in entity and '|' not in title.lower():
            # Check if this looks like "team1 team2" without separator
            words = entity.split()
            if len(words) >= 2:
                # For now, keep as single entity but also try to extract known team patterns
                # This is a simplified approach - in production, use a team name database
                pass
        
        if entity and len(entity) > 1:
            entities.append(entity)
        
        # Also add individual words as potential entities for better matching
        words = entity.split()
        if len(words) > 1:
            for word in words:
                if len(word) > 2 and word not in words_to_remove:
                    entities.append(word)
    
    return set(entities)


def calculate_string_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity between two strings using SequenceMatcher.
    
    Args:
        str1: First string
        str2: Second string
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not str1 or not str2:
        return 0.0
    
    # Use difflib's SequenceMatcher
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def calculate_time_proximity(
    time1: datetime,
    time2: datetime,
    max_diff_hours: float = 24.0,
) -> Decimal:
    """
    Calculate a match score based on time proximity.
    
    Args:
        time1: First event time
        time2: Second event time
        max_diff_hours: Maximum time difference to consider
        
    Returns:
        Score between 0.0 and 1.0
    """
    diff = abs((time1 - time2).total_seconds())
    max_diff_seconds = max_diff_hours * 3600
    
    if diff > max_diff_seconds:
        return Decimal("0")
    
    # Score decreases linearly with time difference
    score = 1.0 - (diff / max_diff_seconds)
    return Decimal(str(min(1.0, max(0.0, score))))


def calculate_entity_overlap(entities1: Set[str], entities2: Set[str]) -> Decimal:
    """
    Calculate overlap score between two sets of entities.
    
    Args:
        entities1: First set of entities
        entities2: Second set of entities
        
    Returns:
        Overlap score between 0.0 and 1.0
    """
    if not entities1 or not entities2:
        return Decimal("0")
    
    # Calculate Jaccard similarity
    intersection = len(entities1 & entities2)
    union = len(entities1 | entities2)
    
    if union == 0:
        return Decimal("0")
    
    return Decimal(str(intersection / union))


def fuzzy_match_events(
    market_a: NormalizedMarket,
    market_b: NormalizedMarket,
    min_title_similarity: float = 0.6,
    min_entity_overlap: float = 0.5,
    max_time_diff_hours: float = 24.0,
) -> MatchResult:
    """
    Perform fuzzy matching between two market events.
    
    Args:
        market_a: First normalized market
        market_b: Second normalized market
        min_title_similarity: Minimum title similarity threshold
        min_entity_overlap: Minimum entity overlap threshold
        max_time_diff_hours: Maximum allowed time difference
        
    Returns:
        MatchResult with match decision and scores
    """
    reasons = []
    
    # Calculate title similarity
    title_sim = calculate_string_similarity(market_a.title, market_b.title)
    
    # Extract and compare entities
    entities_a = extract_entities(market_a.title)
    entities_b = extract_entities(market_b.title)
    entity_overlap = calculate_entity_overlap(entities_a, entities_b)
    
    # Calculate time proximity
    time_proximity = calculate_time_proximity(
        market_a.start_time,
        market_b.start_time,
        max_time_diff_hours,
    )
    time_diff_hours = abs((market_a.start_time - market_b.start_time).total_seconds()) / 3600
    
    # Category matching
    category_match = market_a.category.lower() == market_b.category.lower()
    
    # Calculate composite match score
    # Weight: title similarity 30%, entity overlap 40%, time proximity 20%, category 10%
    composite_score = (
        Decimal(str(title_sim)) * Decimal("0.30") +
        entity_overlap * Decimal("0.40") +
        time_proximity * Decimal("0.20") +
        (Decimal("1") if category_match else Decimal("0")) * Decimal("0.10")
    )
    
    # Determine if it's a match
    is_match = True
    
    # Check thresholds
    if title_sim < min_title_similarity:
        is_match = False
        reasons.append(f"Title similarity {title_sim:.2f} below threshold {min_title_similarity}")
    
    if entity_overlap < min_entity_overlap:
        is_match = False
        reasons.append(f"Entity overlap {float(entity_overlap):.2f} below threshold {min_entity_overlap}")
    
    if time_proximity == 0:
        is_match = False
        reasons.append(f"Time difference exceeds {max_time_diff_hours} hours")
    
    if not category_match:
        is_match = False
        reasons.append("Categories don't match")
    
    if is_match:
        reasons.append("All matching criteria passed")
    
    return MatchResult(
        is_match=is_match,
        score=composite_score,
        reasons=reasons,
        title_similarity=Decimal(str(title_sim)),
        time_proximity_hours=time_diff_hours,
        entity_overlap=entity_overlap,
    )


def map_outcomes(
    market_a: NormalizedMarket,
    market_b: NormalizedMarket,
) -> List[Tuple[MarketOutcome, MarketOutcome, str]]:
    """
    Map equivalent outcomes between two markets.
    
    Returns list of tuples: (outcome_a, outcome_b, mapping_type)
    
    Args:
        market_a: First normalized market
        market_b: Second normalized market
        
    Returns:
        List of mapped outcome pairs with mapping type
    """
    mappings = []
    
    # For binary markets (yes/no, team_a/team_b)
    if market_a.is_binary and market_b.is_binary:
        outcome_a1, outcome_a2 = market_a.outcomes[0], market_a.outcomes[1]
        outcome_b1, outcome_b2 = market_b.outcomes[0], market_b.outcomes[1]
        
        # Check for yes/no mapping
        labels_a = [o.label.lower() for o in market_a.outcomes]
        labels_b = [o.label.lower() for o in market_b.outcomes]
        
        # Try to identify yes/no sides
        yes_terms = {'yes', 'y', 'true', 'over'}
        no_terms = {'no', 'n', 'false', 'under'}
        
        a_has_yes = any(l in yes_terms for l in labels_a)
        a_has_no = any(l in no_terms for l in labels_a)
        b_has_yes = any(l in yes_terms for l in labels_b)
        b_has_no = any(l in no_terms for l in labels_b)
        
        if a_has_yes and a_has_no and b_has_yes and b_has_no:
            # Binary yes/no mapping - match yes with yes, no with no
            a_yes = next(o for o in market_a.outcomes if o.label.lower() in yes_terms)
            a_no = next(o for o in market_a.outcomes if o.label.lower() in no_terms)
            b_yes = next(o for o in market_b.outcomes if o.label.lower() in yes_terms)
            b_no = next(o for o in market_b.outcomes if o.label.lower() in no_terms)
            
            mappings.append((a_yes, b_yes, "yes_vs_yes"))
            mappings.append((a_no, b_no, "no_vs_no"))
        else:
            # Try to map by entity names
            entities_a = extract_entities(market_a.title)
            entities_b = extract_entities(market_b.title)
            
            # Map outcomes based on entity similarity
            for out_a in market_a.outcomes:
                out_a_label = out_a.label.lower()
                for out_b in market_b.outcomes:
                    out_b_label = out_b.label.lower()
                    
                    # Direct label match
                    if out_a_label == out_b_label:
                        mappings.append((out_a, out_b, "direct_match"))
                    # Check if outcome labels contain matching entities
                    elif any(e in out_a_label for e in entities_a) and any(e in out_b_label for e in entities_b):
                        if calculate_string_similarity(out_a_label, out_b_label) > 0.6:
                            mappings.append((out_a, out_b, "entity_match"))
    
    return mappings


class EventMatcher:
    """
    High-level event matcher that coordinates fuzzy matching and outcome mapping.
    
    This class provides a configurable interface for matching events across
    different sources with customizable thresholds.
    """
    
    def __init__(
        self,
        min_match_score: Decimal = Decimal("0.75"),
        min_title_similarity: float = 0.6,
        min_entity_overlap: float = 0.5,
        max_time_diff_hours: float = 24.0,
        require_same_market_type: bool = True,
    ):
        """
        Initialize the EventMatcher with configuration.
        
        Args:
            min_match_score: Minimum composite score to consider a match
            min_title_similarity: Minimum title similarity threshold
            min_entity_overlap: Minimum entity overlap threshold
            max_time_diff_hours: Maximum allowed time difference
            require_same_market_type: Whether markets must be the same type
        """
        self.min_match_score = min_match_score
        self.min_title_similarity = min_title_similarity
        self.min_entity_overlap = min_entity_overlap
        self.max_time_diff_hours = max_time_diff_hours
        self.require_same_market_type = require_same_market_type
    
    def match(
        self,
        market_a: NormalizedMarket,
        market_b: NormalizedMarket,
    ) -> Optional[MatchedEvent]:
        """
        Attempt to match two markets.
        
        Args:
            market_a: First normalized market
            market_b: Second normalized market
            
        Returns:
            MatchedEvent if markets match, None otherwise
        """
        # Check market type requirement
        if self.require_same_market_type and market_a.market_type != market_b.market_type:
            return None
        
        # Perform fuzzy matching
        match_result = fuzzy_match_events(
            market_a,
            market_b,
            min_title_similarity=self.min_title_similarity,
            min_entity_overlap=self.min_entity_overlap,
            max_time_diff_hours=self.max_time_diff_hours,
        )
        
        # Check if match score meets threshold
        if not match_result.is_match or match_result.score < self.min_match_score:
            return MatchedEvent(
                left_market=market_a,
                right_market=market_b,
                match_score=match_result.score,
                status="rejected",
                rejection_reason="; ".join(match_result.reasons),
            )
        
        # Map outcomes
        outcome_mappings = map_outcomes(market_a, market_b)
        
        if not outcome_mappings:
            return MatchedEvent(
                left_market=market_a,
                right_market=market_b,
                match_score=match_result.score,
                status="rejected",
                rejection_reason="Could not map outcomes between markets",
            )
        
        # Calculate resolution confidence based on match quality
        resolution_confidence = match_result.score * Decimal("0.95")  # Small penalty for uncertainty
        
        return MatchedEvent(
            left_market=market_a,
            right_market=market_b,
            match_score=match_result.score,
            resolution_confidence=resolution_confidence,
            mapping_type=outcome_mappings[0][2] if outcome_mappings else "unknown",
            status="matched",
        )
    
    def find_matches(
        self,
        markets_a: List[NormalizedMarket],
        markets_b: List[NormalizedMarket],
    ) -> List[MatchedEvent]:
        """
        Find all matches between two lists of markets.
        
        Args:
            markets_a: First list of markets
            markets_b: Second list of markets
            
        Returns:
            List of matched events
        """
        matches = []
        matched_b_ids = set()
        
        for market_a in markets_a:
            best_match = None
            best_score = Decimal("0")
            
            for market_b in markets_b:
                if market_b.source_event_id in matched_b_ids:
                    continue
                
                result = self.match(market_a, market_b)
                if result and result.status == "matched" and result.match_score > best_score:
                    best_match = result
                    best_score = result.match_score
            
            if best_match:
                matches.append(best_match)
                matched_b_ids.add(best_match.right_market.source_event_id)
        
        return matches
    
    def batch_match(
        self,
        markets: List[NormalizedMarket],
        group_by: str = "category",
    ) -> List[MatchedEvent]:
        """
        Find matches within a single list of markets (cross-source matching).
        
        Args:
            markets: List of markets from various sources
            group_by: Attribute to group markets by before matching
            
        Returns:
            List of matched events
        """
        # Group markets by the specified attribute
        groups = {}
        for market in markets:
            key = getattr(market, group_by, "unknown")
            if key not in groups:
                groups[key] = []
            groups[key].append(market)
        
        # Find matches within each group (different sources only)
        all_matches = []
        for group_key, group_markets in groups.items():
            # Separate by source
            sources = {}
            for m in group_markets:
                if m.source not in sources:
                    sources[m.source] = []
                sources[m.source].append(m)
            
            # Match each source against others
            source_names = list(sources.keys())
            for i, source_a in enumerate(source_names):
                for source_b in source_names[i + 1:]:
                    matches = self.find_matches(
                        sources[source_a],
                        sources[source_b],
                    )
                    all_matches.extend(matches)
        
        return all_matches
