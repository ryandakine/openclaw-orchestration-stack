"""
Matcher Pipeline - O(n×m) matching with early exit optimization.

Module 2.9: Core matching pipeline that pairs prediction market events
with sportsbook events, filtering by min_score and returning validated
MatchedOpportunity objects.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from category_validator import CategoryValidator, get_validator
from date_matcher import DateMatcher, get_date_matcher
from entity_extractor import EntityExtractor, ExtractionContext, get_extractor
from match_rejection_logger import MatchRejectionLogger, get_rejection_logger
from match_result_schema import (
    EntitySet,
    MappingType,
    MatchResult,
    MatchScores,
    MatchStatus,
    MatchedOpportunity,
    RejectionReason,
)
from match_scorer import MatchScorer, get_scorer
from outcome_mapper import OutcomeMapper, get_mapper
from resolution_semantics import ResolutionSemanticsAnalyzer, get_analyzer
from title_similarity import TitleSimilarityScorer, get_scorer as get_title_scorer


@dataclass
class PipelineConfig:
    """Configuration for the matcher pipeline."""
    min_match_score: float = 0.85
    min_title_score: float = 0.60
    min_category_score: float = 0.50
    max_candidates_per_event: int = 50
    early_exit_threshold: float = 0.95
    enable_parallel: bool = True
    max_workers: int = 4


class MatcherPipeline:
    """
    O(n×m) matching pipeline with early exit optimization.
    
    Pipeline flow:
    1. Filter by category (early reject)
    2. Score title similarity
    3. Extract and match entities
    4. Match dates
    5. Compare resolution semantics
    6. Calculate final score
    7. Filter by min_score
    8. Map outcomes
    9. Return MatchedOpportunity list
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or self._load_config_from_env()
        
        # Initialize components
        self.title_scorer = get_title_scorer()
        self.entity_extractor = get_extractor()
        self.date_matcher = get_date_matcher()
        self.category_validator = get_validator()
        self.resolution_analyzer = get_analyzer()
        self.match_scorer = get_scorer()
        self.outcome_mapper = get_mapper()
        self.rejection_logger = get_rejection_logger()
    
    def _load_config_from_env(self) -> PipelineConfig:
        """Load pipeline configuration from environment variables."""
        return PipelineConfig(
            min_match_score=float(
                os.getenv("OPENCLAW_MIN_MATCH_SCORE", "0.85")
            ),
            min_title_score=float(
                os.getenv("OPENCLAW_MIN_TITLE_SCORE_PIPELINE", "0.60")
            ),
            min_category_score=float(
                os.getenv("OPENCLAW_MIN_CATEGORY_SCORE", "0.50")
            ),
            max_candidates_per_event=int(
                os.getenv("OPENCLAW_MAX_CANDIDATES", "50")
            ),
            early_exit_threshold=float(
                os.getenv("OPENCLAW_EARLY_EXIT_THRESHOLD", "0.95")
            ),
            enable_parallel=os.getenv("OPENCLAW_ENABLE_PARALLEL", "true").lower() == "true",
            max_workers=int(os.getenv("OPENCLAW_MAX_WORKERS", "4")),
        )
    
    async def match(
        self,
        pm_events: list[dict[str, Any]],
        sb_events: list[dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[MatchedOpportunity]:
        """
        Match prediction market events against sportsbook events.
        
        Args:
            pm_events: List of prediction market event dicts
            sb_events: List of sportsbook event dicts
            progress_callback: Optional callback(current, total)
        
        Returns:
            List of validated MatchedOpportunity objects
        """
        opportunities: list[MatchedOpportunity] = []
        total_comparisons = len(pm_events) * len(sb_events)
        current_comparison = 0
        
        # Pre-extract entities for all PM events (optimization)
        pm_entities: dict[str, EntitySet] = {}
        for pm in pm_events:
            pm_id = pm.get("id", "")
            pm_entities[pm_id] = self._extract_pm_entities(pm)
        
        for pm_event in pm_events:
            pm_id = pm_event.get("id", "")
            pm_title = pm_event.get("title", "")
            pm_category = pm_event.get("category", "")
            pm_date = pm_event.get("event_date", "")
            
            best_match: Optional[MatchResult] = None
            candidate_count = 0
            
            for sb_event in sb_events:
                current_comparison += 1
                
                if progress_callback and current_comparison % 10 == 0:
                    progress_callback(current_comparison, total_comparisons)
                
                # Limit candidates per event for performance
                if candidate_count >= self.config.max_candidates_per_event:
                    break
                
                # Run matching logic
                match_result = await self._match_pair(
                    pm_event,
                    sb_event,
                    pm_entities.get(pm_id, EntitySet()),
                )
                
                # Track best match for this PM event
                if match_result.status == MatchStatus.MATCHED:
                    if best_match is None or match_result.match_score > best_match.match_score:
                        best_match = match_result
                    
                    # Early exit if we found an excellent match
                    if match_result.match_score >= self.config.early_exit_threshold:
                        break
                
                candidate_count += 1
            
            # Convert best match to opportunity
            if best_match and best_match.match_score >= self.config.min_match_score:
                opportunity = self._create_opportunity(best_match)
                opportunities.append(opportunity)
        
        return opportunities
    
    async def _match_pair(
        self,
        pm_event: dict[str, Any],
        sb_event: dict[str, Any],
        pm_entities: EntitySet,
    ) -> MatchResult:
        """Match a single PM-SB pair and return MatchResult."""
        match_result = MatchResult(
            left_source=pm_event.get("source", "polymarket"),
            left_event_id=pm_event.get("id", ""),
            left_event_title=pm_event.get("title", ""),
            left_category=pm_event.get("category", ""),
            left_resolution_rules=pm_event.get("resolution_rules", ""),
            left_entities=pm_entities,
            left_outcome=pm_event.get("outcome", "YES"),
            left_odds=pm_event.get("odds", 0.0),
            right_source=sb_event.get("source", "sportsbook"),
            right_event_id=sb_event.get("id", ""),
            right_event_title=sb_event.get("title", ""),
            right_category=sb_event.get("category", ""),
            right_resolution_rules=sb_event.get("resolution_rules", ""),
            right_outcome=sb_event.get("outcome", ""),
            right_odds=sb_event.get("odds", 0.0),
        )
        
        # Step 1: Category validation (early reject)
        should_reject, reason = self.category_validator.should_reject_early(
            match_result.left_category,
            match_result.right_category,
        )
        if should_reject:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.CATEGORY_MISMATCH
            match_result.rejection_details = reason
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        cat_score, _ = self.category_validator.validate(
            match_result.left_category,
            match_result.right_category,
        )
        
        if cat_score < self.config.min_category_score:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.CATEGORY_MISMATCH
            match_result.rejection_details = f"Category score too low: {cat_score:.2f}"
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        # Step 2: Title similarity
        title_score = self.title_scorer.score(
            match_result.left_event_title,
            match_result.right_event_title,
        )
        
        if title_score < self.config.min_title_score:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.LOW_TITLE_SIMILARITY
            match_result.rejection_details = f"Title score too low: {title_score:.2f}"
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        # Step 3: Entity extraction and matching (for SB event)
        sb_entities = self._extract_sb_entities(sb_event)
        match_result.right_entities = sb_entities
        
        entity_score = self._calculate_entity_match(pm_entities, sb_entities)
        
        # Step 4: Date matching
        date_score = self.date_matcher.match(
            match_result.left_event_title + " " + str(pm_event.get("event_date", "")),
            match_result.right_event_title + " " + str(sb_event.get("event_date", "")),
            match_result.left_category,
        )
        
        if date_score == 0.0:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.DATE_MISMATCH
            match_result.rejection_details = "Date mismatch"
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        # Step 5: Resolution semantics
        resolution_score = 1.0
        if match_result.left_resolution_rules and match_result.right_resolution_rules:
            resolution_score, _, _ = self.resolution_analyzer.compare(
                match_result.left_resolution_rules,
                match_result.right_resolution_rules,
            )
            
            if resolution_score < 0.5:
                match_result.status = MatchStatus.REJECTED
                match_result.rejection_reason = RejectionReason.RESOLUTION_SEMANTICS_MISMATCH
                match_result.rejection_details = f"Resolution semantics mismatch: {resolution_score:.2f}"
                await self.rejection_logger.log_rejection(match_result)
                return match_result
        
        # Step 6: Calculate final score
        scores = self.match_scorer.calculate(
            title_similarity=title_score,
            entity_match=entity_score,
            date_match=date_score,
            category_match=cat_score,
            resolution_semantics=resolution_score,
        )
        
        match_result.scores = scores
        match_result.match_score = scores.final_score
        
        if scores.final_score < self.config.min_match_score:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.LOW_OVERALL_SCORE
            match_result.rejection_details = f"Final score too low: {scores.final_score:.2f}"
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        # Step 7: Outcome mapping
        outcome_mapping = self.outcome_mapper.map_outcomes(
            match_result.left_outcome,
            match_result.right_outcome,
            match_result.left_event_title,
            match_result.right_event_title,
        )
        
        # Determine mapping type
        if outcome_mapping.direction.value == "inverse":
            match_result.mapping_type = MappingType.INVERSE
        elif outcome_mapping.direction.value == "direct":
            match_result.mapping_type = MappingType.DIRECT
        else:
            match_result.mapping_type = MappingType.UNKNOWN
        
        # Calculate resolution confidence
        match_result.resolution_confidence = min(
            resolution_score,
            outcome_mapping.confidence,
        )
        
        if match_result.resolution_confidence < 0.9:
            match_result.status = MatchStatus.REJECTED
            match_result.rejection_reason = RejectionReason.RESOLUTION_SEMANTICS_MISMATCH
            match_result.rejection_details = f"Resolution confidence too low: {match_result.resolution_confidence:.2f}"
            await self.rejection_logger.log_rejection(match_result)
            return match_result
        
        # Mark as matched
        match_result.status = MatchStatus.MATCHED
        
        return match_result
    
    def _extract_pm_entities(self, pm_event: dict[str, Any]) -> EntitySet:
        """Extract entities from a prediction market event."""
        context = ExtractionContext(
            category=pm_event.get("category", ""),
            source=pm_event.get("source", "polymarket"),
        )
        
        return self.entity_extractor.extract(
            title=pm_event.get("title", ""),
            description=pm_event.get("description", ""),
            context=context,
        )
    
    def _extract_sb_entities(self, sb_event: dict[str, Any]) -> EntitySet:
        """Extract entities from a sportsbook event."""
        context = ExtractionContext(
            category=sb_event.get("category", ""),
            source=sb_event.get("source", "sportsbook"),
        )
        
        return self.entity_extractor.extract(
            title=sb_event.get("title", ""),
            description=sb_event.get("description", ""),
            context=context,
        )
    
    def _calculate_entity_match(
        self,
        pm_entities: EntitySet,
        sb_entities: EntitySet,
    ) -> float:
        """Calculate entity match score between two entity sets."""
        scores: list[float] = []
        
        # Candidate match
        if pm_entities.candidates and sb_entities.candidates:
            intersection = pm_entities.candidates & sb_entities.candidates
            union = pm_entities.candidates | sb_entities.candidates
            if union:
                scores.append(len(intersection) / len(union))
        
        # Team match
        if pm_entities.teams and sb_entities.teams:
            intersection = pm_entities.teams & sb_entities.teams
            union = pm_entities.teams | sb_entities.teams
            if union:
                scores.append(len(intersection) / len(union))
        
        # Player match
        if pm_entities.players and sb_entities.players:
            intersection = pm_entities.players & sb_entities.players
            union = pm_entities.players | sb_entities.players
            if union:
                scores.append(len(intersection) / len(union))
        
        if not scores:
            return 0.5  # Neutral if no entities
        
        return sum(scores) / len(scores)
    
    def _create_opportunity(self, match_result: MatchResult) -> MatchedOpportunity:
        """Create a MatchedOpportunity from a MatchResult."""
        opportunity = MatchedOpportunity(
            match_result=match_result,
            confidence_tier=self.match_scorer.get_confidence_tier(match_result.match_score),
        )
        
        # Calculate implied probabilities
        opportunity.calculate_implied_probabilities()
        
        return opportunity


# Singleton instance
_default_pipeline: Optional[MatcherPipeline] = None


def get_pipeline() -> MatcherPipeline:
    """Get the default matcher pipeline instance."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = MatcherPipeline()
    return _default_pipeline


async def run_matching(
    pm_events: list[dict[str, Any]],
    sb_events: list[dict[str, Any]],
    min_score: Optional[float] = None,
) -> list[MatchedOpportunity]:
    """
    Convenience function to run the matching pipeline.
    
    Args:
        pm_events: Prediction market events
        sb_events: Sportsbook events
        min_score: Optional minimum match score override
    
    Returns:
        List of matched opportunities
    """
    pipeline = get_pipeline()
    
    if min_score is not None:
        pipeline.config.min_match_score = min_score
    
    return await pipeline.match(pm_events, sb_events)
