"""
Match Scorer - Combine component scores into final match confidence.

Module 2.7: Combines title similarity (40%), entity match (30%), 
date match (20%), and category match (10%) into a final 0-1 score.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from match_result_schema import EntitySet, MatchScores


# Default weights for component scores
DEFAULT_WEIGHTS = {
    "title_similarity": 0.40,
    "entity_match": 0.30,
    "date_match": 0.20,
    "category_match": 0.10,
}


@dataclass
class ScoringConfig:
    """Configuration for match scoring."""
    weights: dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    min_title_score: float = 0.50
    min_entity_score: float = 0.30
    min_date_score: float = 0.30
    min_category_score: float = 0.50
    min_final_score: float = 0.85
    require_all_components: bool = False


class EntityMatcher:
    """Matches entities between two entity sets."""
    
    def match(self, entities1: EntitySet, entities2: EntitySet) -> float:
        """
        Calculate entity match score between two entity sets.
        
        Returns:
            Float between 0 and 1
        """
        scores: list[float] = []
        
        # Candidate match
        if entities1.candidates or entities2.candidates:
            candidate_score = self._match_frozensets(
                entities1.candidates, entities2.candidates
            )
            scores.append(candidate_score)
        
        # Team match
        if entities1.teams or entities2.teams:
            team_score = self._match_frozensets(entities1.teams, entities2.teams)
            scores.append(team_score)
        
        # Player match
        if entities1.players or entities2.players:
            player_score = self._match_frozensets(entities1.players, entities2.players)
            scores.append(player_score)
        
        # Date match (already handled by date_matcher, but check for consistency)
        if entities1.dates or entities2.dates:
            date_score = self._match_frozensets(entities1.dates, entities2.dates)
            scores.append(date_score)
        
        # Location match
        if entities1.locations or entities2.locations:
            location_score = self._match_frozensets(
                entities1.locations, entities2.locations
            )
            scores.append(location_score)
        
        # Organization match
        if entities1.organizations or entities2.organizations:
            org_score = self._match_frozensets(
                entities1.organizations, entities2.organizations
            )
            scores.append(org_score)
        
        if not scores:
            return 0.5  # Neutral if no entities to compare
        
        # Weight by number of entities found
        # More entities = more confident in match
        weighted_scores = []
        for score in scores:
            # Boost scores when we have more data
            weighted_scores.append(score)
        
        return sum(weighted_scores) / len(weighted_scores)
    
    def _match_frozensets(self, set1: frozenset[str], set2: frozenset[str]) -> float:
        """Match two frozensets of strings."""
        if not set1 and not set2:
            return 0.5  # Neutral
        
        if not set1 or not set2:
            return 0.0  # One has entities, other doesn't
        
        # Check for intersection (exact matches)
        intersection = set1 & set2
        
        # Check for partial matches (case-insensitive, substring)
        partial_matches = 0
        for item1 in set1:
            item1_lower = item1.lower()
            for item2 in set2:
                item2_lower = item2.lower()
                if item1_lower == item2_lower:
                    continue  # Already counted in intersection
                if item1_lower in item2_lower or item2_lower in item1_lower:
                    partial_matches += 0.5
        
        total_matches = len(intersection) + partial_matches
        max_possible = max(len(set1), len(set2))
        
        if max_possible == 0:
            return 0.5
        
        return min(1.0, total_matches / max_possible)


class MatchScorer:
    """
    Combines component scores into a final match confidence score.
    
    Weights:
    - Title similarity: 40%
    - Entity match: 30%
    - Date match: 20%
    - Category match: 10%
    """
    
    def __init__(self, config: Optional[ScoringConfig] = None) -> None:
        self.config = config or self._load_config_from_env()
        self.entity_matcher = EntityMatcher()
    
    def _load_config_from_env(self) -> ScoringConfig:
        """Load scoring configuration from environment variables."""
        config = ScoringConfig()
        
        # Load weights
        for key in DEFAULT_WEIGHTS:
            env_val = os.getenv(f"OPENCLAW_SCORE_WEIGHT_{key.upper()}")
            if env_val:
                config.weights[key] = float(env_val)
        
        # Load minimums
        config.min_title_score = float(
            os.getenv("OPENCLAW_MIN_TITLE_SCORE", str(config.min_title_score))
        )
        config.min_entity_score = float(
            os.getenv("OPENCLAW_MIN_ENTITY_SCORE", str(config.min_entity_score))
        )
        config.min_date_score = float(
            os.getenv("OPENCLAW_MIN_DATE_SCORE", str(config.min_date_score))
        )
        config.min_category_score = float(
            os.getenv("OPENCLAW_MIN_CATEGORY_SCORE", str(config.min_category_score))
        )
        config.min_final_score = float(
            os.getenv("OPENCLAW_MIN_FINAL_SCORE", str(config.min_final_score))
        )
        config.require_all_components = (
            os.getenv("OPENCLAW_REQUIRE_ALL_COMPONENTS", "false").lower() == "true"
        )
        
        return config
    
    def calculate(
        self,
        title_similarity: float,
        entity_match: float,
        date_match: float,
        category_match: float,
        resolution_semantics: float = 1.0,
    ) -> MatchScores:
        """
        Calculate final match score from component scores.
        
        Args:
            title_similarity: 0-1 title similarity score
            entity_match: 0-1 entity match score
            date_match: 0-1 date match score
            category_match: 0-1 category match score
            resolution_semantics: 0-1 resolution semantics match score
        
        Returns:
            MatchScores with component and final scores
        """
        weights = self.config.weights
        
        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight != 1.0:
            weights = {k: v / total_weight for k, v in weights.items()}
        
        # Calculate weighted final score
        final_score = (
            title_similarity * weights.get("title_similarity", 0.40) +
            entity_match * weights.get("entity_match", 0.30) +
            date_match * weights.get("date_match", 0.20) +
            category_match * weights.get("category_match", 0.10)
        )
        
        # Apply resolution semantics penalty if significantly different
        if resolution_semantics < 0.8:
            final_score *= resolution_semantics
        
        # Check minimum thresholds
        if self.config.require_all_components:
            if title_similarity < self.config.min_title_score:
                final_score *= 0.5
            if entity_match < self.config.min_entity_score:
                final_score *= 0.5
            if date_match < self.config.min_date_score:
                final_score *= 0.5
            if category_match < self.config.min_category_score:
                final_score *= 0.5
        
        return MatchScores(
            title_similarity=title_similarity,
            entity_match=entity_match,
            date_match=date_match,
            category_match=category_match,
            resolution_semantics=resolution_semantics,
            final_score=round(final_score, 4),
        )
    
    def calculate_from_entities(
        self,
        title_similarity: float,
        entities1: EntitySet,
        entities2: EntitySet,
        date_match: float,
        category_match: float,
        resolution_semantics: float = 1.0,
    ) -> MatchScores:
        """
        Calculate match score with automatic entity matching.
        
        Args:
            title_similarity: 0-1 title similarity score
            entities1: First entity set
            entities2: Second entity set
            date_match: 0-1 date match score
            category_match: 0-1 category match score
            resolution_semantics: 0-1 resolution semantics match score
        
        Returns:
            MatchScores with component and final scores
        """
        entity_match = self.entity_matcher.match(entities1, entities2)
        
        return self.calculate(
            title_similarity=title_similarity,
            entity_match=entity_match,
            date_match=date_match,
            category_match=category_match,
            resolution_semantics=resolution_semantics,
        )
    
    def is_match(self, scores: MatchScores) -> bool:
        """Check if match scores meet the minimum threshold."""
        return scores.final_score >= self.config.min_final_score
    
    def explain_score(self, scores: MatchScores) -> dict:
        """Return human-readable explanation of the score."""
        weights = self.config.weights
        
        components = {
            "title_similarity": {
                "score": scores.title_similarity,
                "weight": weights.get("title_similarity", 0.40),
                "weighted": scores.title_similarity * weights.get("title_similarity", 0.40),
                "passed": scores.title_similarity >= self.config.min_title_score,
            },
            "entity_match": {
                "score": scores.entity_match,
                "weight": weights.get("entity_match", 0.30),
                "weighted": scores.entity_match * weights.get("entity_match", 0.30),
                "passed": scores.entity_match >= self.config.min_entity_score,
            },
            "date_match": {
                "score": scores.date_match,
                "weight": weights.get("date_match", 0.20),
                "weighted": scores.date_match * weights.get("date_match", 0.20),
                "passed": scores.date_match >= self.config.min_date_score,
            },
            "category_match": {
                "score": scores.category_match,
                "weight": weights.get("category_match", 0.10),
                "weighted": scores.category_match * weights.get("category_match", 0.10),
                "passed": scores.category_match >= self.config.min_category_score,
            },
            "resolution_semantics": {
                "score": scores.resolution_semantics,
                "impact": "penalty" if scores.resolution_semantics < 0.8 else "none",
            },
        }
        
        return {
            "final_score": scores.final_score,
            "is_match": self.is_match(scores),
            "components": components,
            "threshold": self.config.min_final_score,
        }
    
    def get_confidence_tier(self, score: float) -> str:
        """
        Get confidence tier for a score.
        
        Returns:
            "A" (high), "B" (medium), "C" (low), or "F" (reject)
        """
        if score >= 0.95:
            return "A"
        elif score >= 0.90:
            return "B"
        elif score >= 0.85:
            return "C"
        else:
            return "F"


# Singleton instance
_default_scorer: Optional[MatchScorer] = None


def get_scorer() -> MatchScorer:
    """Get the default match scorer instance."""
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = MatchScorer()
    return _default_scorer


def calculate_match_score(
    title_similarity: float,
    entity_match: float,
    date_match: float,
    category_match: float,
    resolution_semantics: float = 1.0,
) -> MatchScores:
    """Convenience function to calculate match score."""
    return get_scorer().calculate(
        title_similarity, entity_match, date_match, category_match, resolution_semantics
    )


def is_valid_match(scores: MatchScores, min_score: float = 0.85) -> bool:
    """Convenience function to check if scores represent a valid match."""
    return scores.final_score >= min_score
