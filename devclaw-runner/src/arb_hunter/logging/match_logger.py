"""
match_logger.py - Log match operations including count, scores, confidence, and rejects.

Tracks the matching process between markets from different sources, including
match scores, resolution confidence, and rejection reasons.
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import structlog

from .logger_config import get_logger


class MatchResolution(str, Enum):
    """Resolution confidence level for a match."""
    HIGH = "high"  # > 90% confidence
    MEDIUM = "medium"  # 70-90% confidence
    LOW = "low"  # 50-70% confidence
    REJECTED = "rejected"  # < 50% confidence


class MatchType(str, Enum):
    """Type of match between markets."""
    EXACT = "exact"  # Perfect match
    FUZZY = "fuzzy"  # Fuzzy name matching
    EVENT_BASED = "event_based"  # Matched via event context
    MANUAL = "manual"  # Manually confirmed
    DERIVED = "derived"  # Derived from existing matches


@dataclass
class MatchRecord:
    """Record of a single market match."""
    match_id: str
    run_id: str
    source_a: str
    market_id_a: str
    source_b: str
    market_id_b: str
    match_score: float  # 0.0 to 1.0
    resolution_confidence: MatchResolution
    match_type: MatchType
    match_factors: Dict[str, float] = field(default_factory=dict)
    # Individual factor scores
    name_similarity: Optional[float] = None
    time_proximity: Optional[float] = None
    participant_overlap: Optional[float] = None
    league_match: Optional[float] = None
    price_correlation: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["resolution_confidence"] = self.resolution_confidence.value
        result["match_type"] = self.match_type.value
        return result


@dataclass
class MatchBatchRecord:
    """Record of a batch matching operation."""
    batch_id: str
    run_id: str
    source_a: str
    source_b: str
    markets_in_a: int = 0
    markets_in_b: int = 0
    comparisons_made: int = 0
    matches_found: int = 0
    high_confidence_matches: int = 0
    medium_confidence_matches: int = 0
    low_confidence_matches: int = 0
    rejected_matches: int = 0
    processing_time_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


class MatchLogger:
    """
    Logger for market matching operations.
    
    Tracks the process of matching markets between different bookmakers,
    including match scores, confidence levels, and rejection reasons.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("match_logger")
        self.log_dir = Path(log_dir) if log_dir else None
        self._match_records: List[MatchRecord] = []
        self._batch_records: List[MatchBatchRecord] = []
    
    def log_match(
        self,
        match_id: str,
        run_id: str,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        match_score: float,
        resolution_confidence: MatchResolution,
        match_type: MatchType,
        name_similarity: Optional[float] = None,
        time_proximity: Optional[float] = None,
        participant_overlap: Optional[float] = None,
        league_match: Optional[float] = None,
        price_correlation: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MatchRecord:
        """
        Log a single market match.
        
        Args:
            match_id: Unique match identifier
            run_id: Parent run ID
            source_a: First bookmaker source
            market_id_a: Market ID from source A
            source_b: Second bookmaker source
            market_id_b: Market ID from source B
            match_score: Overall match score (0.0 to 1.0)
            resolution_confidence: Confidence level enum
            match_type: Type of match
            name_similarity: Name similarity score
            time_proximity: Time proximity score
            participant_overlap: Participant overlap score
            league_match: League matching score
            price_correlation: Price correlation score
            metadata: Additional metadata
            
        Returns:
            The MatchRecord
        """
        # Build match factors dict
        match_factors = {}
        if name_similarity is not None:
            match_factors["name_similarity"] = name_similarity
        if time_proximity is not None:
            match_factors["time_proximity"] = time_proximity
        if participant_overlap is not None:
            match_factors["participant_overlap"] = participant_overlap
        if league_match is not None:
            match_factors["league_match"] = league_match
        if price_correlation is not None:
            match_factors["price_correlation"] = price_correlation
        
        record = MatchRecord(
            match_id=match_id,
            run_id=run_id,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            match_score=match_score,
            resolution_confidence=resolution_confidence,
            match_type=match_type,
            match_factors=match_factors,
            name_similarity=name_similarity,
            time_proximity=time_proximity,
            participant_overlap=participant_overlap,
            league_match=league_match,
            price_correlation=price_correlation,
            metadata=metadata or {}
        )
        
        self._match_records.append(record)
        
        # Determine log level based on confidence
        if resolution_confidence == MatchResolution.HIGH:
            log_level = "info"
        elif resolution_confidence == MatchResolution.MEDIUM:
            log_level = "debug"
        elif resolution_confidence == MatchResolution.LOW:
            log_level = "debug"
        else:
            log_level = "warning"
        
        log_method = getattr(self.logger, log_level)
        
        log_method(
            "market_matched",
            match_id=match_id,
            run_id=run_id,
            source_a=source_a,
            source_b=source_b,
            match_score=round(match_score, 4),
            resolution_confidence=resolution_confidence.value,
            match_type=match_type.value,
            match_factors={k: round(v, 4) for k, v in match_factors.items()}
        )
        
        return record
    
    def log_match_rejected(
        self,
        match_id: str,
        run_id: str,
        source_a: str,
        market_id_a: str,
        source_b: str,
        market_id_b: str,
        match_score: float,
        rejection_reason: str,
        rejection_details: Optional[Dict[str, Any]] = None,
        match_factors: Optional[Dict[str, float]] = None
    ) -> MatchRecord:
        """
        Log a match that was rejected due to low confidence.
        
        Args:
            match_id: Unique match identifier
            run_id: Parent run ID
            source_a: First bookmaker source
            market_id_a: Market ID from source A
            source_b: Second bookmaker source
            market_id_b: Market ID from source B
            match_score: Match score that led to rejection
            rejection_reason: Primary reason for rejection
            rejection_details: Detailed rejection information
            match_factors: Individual factor scores
            
        Returns:
            The rejected MatchRecord
        """
        record = MatchRecord(
            match_id=match_id,
            run_id=run_id,
            source_a=source_a,
            market_id_a=market_id_a,
            source_b=source_b,
            market_id_b=market_id_b,
            match_score=match_score,
            resolution_confidence=MatchResolution.REJECTED,
            match_type=MatchType.FUZZY,
            match_factors=match_factors or {},
            metadata={
                "rejection_reason": rejection_reason,
                "rejection_details": rejection_details or {}
            }
        )
        
        self._match_records.append(record)
        
        self.logger.info(
            "match_rejected",
            match_id=match_id,
            run_id=run_id,
            source_a=source_a,
            source_b=source_b,
            match_score=round(match_score, 4),
            rejection_reason=rejection_reason,
            match_factors={k: round(v, 4) for k, v in (match_factors or {}).items()}
        )
        
        return record
    
    def log_batch_start(
        self,
        batch_id: str,
        run_id: str,
        source_a: str,
        source_b: str,
        markets_in_a: int,
        markets_in_b: int
    ) -> MatchBatchRecord:
        """
        Log the start of a batch matching operation.
        
        Args:
            batch_id: Unique batch identifier
            run_id: Parent run ID
            source_a: First source name
            source_b: Second source name
            markets_in_a: Number of markets in source A
            markets_in_b: Number of markets in source B
            
        Returns:
            The MatchBatchRecord
        """
        record = MatchBatchRecord(
            batch_id=batch_id,
            run_id=run_id,
            source_a=source_a,
            source_b=source_b,
            markets_in_a=markets_in_a,
            markets_in_b=markets_in_b,
            comparisons_made=markets_in_a * markets_in_b
        )
        
        self._batch_records.append(record)
        
        self.logger.info(
            "match_batch_started",
            batch_id=batch_id,
            run_id=run_id,
            source_a=source_a,
            source_b=source_b,
            markets_in_a=markets_in_a,
            markets_in_b=markets_in_b,
            estimated_comparisons=record.comparisons_made
        )
        
        return record
    
    def log_batch_complete(
        self,
        batch_id: str,
        matches_found: int,
        high_confidence: int = 0,
        medium_confidence: int = 0,
        low_confidence: int = 0,
        rejected: int = 0,
        processing_time_ms: Optional[float] = None
    ) -> None:
        """
        Log completion of a batch matching operation.
        
        Args:
            batch_id: Batch identifier
            matches_found: Total matches found
            high_confidence: High confidence match count
            medium_confidence: Medium confidence match count
            low_confidence: Low confidence match count
            rejected: Rejected match count
            processing_time_ms: Processing time in milliseconds
        """
        # Find and update the batch record
        for record in self._batch_records:
            if record.batch_id == batch_id:
                record.matches_found = matches_found
                record.high_confidence_matches = high_confidence
                record.medium_confidence_matches = medium_confidence
                record.low_confidence_matches = low_confidence
                record.rejected_matches = rejected
                record.processing_time_ms = processing_time_ms
                break
        
        self.logger.info(
            "match_batch_completed",
            batch_id=batch_id,
            matches_found=matches_found,
            high_confidence=high_confidence,
            medium_confidence=medium_confidence,
            low_confidence=low_confidence,
            rejected=rejected,
            processing_time_ms=round(processing_time_ms, 2) if processing_time_ms else None
        )
    
    def get_match_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of matches.
        
        Args:
            run_id: Filter by run ID (optional)
            
        Returns:
            Summary dictionary
        """
        records = self._match_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        total = len(records)
        by_confidence = {
            "high": len([r for r in records if r.resolution_confidence == MatchResolution.HIGH]),
            "medium": len([r for r in records if r.resolution_confidence == MatchResolution.MEDIUM]),
            "low": len([r for r in records if r.resolution_confidence == MatchResolution.LOW]),
            "rejected": len([r for r in records if r.resolution_confidence == MatchResolution.REJECTED])
        }
        
        by_type = {}
        for match_type in MatchType:
            count = len([r for r in records if r.match_type == match_type])
            if count > 0:
                by_type[match_type.value] = count
        
        # Average match score
        avg_score = sum(r.match_score for r in records) / total if total > 0 else 0
        
        # By source pair
        by_source_pair: Dict[str, int] = {}
        for record in records:
            pair = f"{record.source_a}:{record.source_b}"
            by_source_pair[pair] = by_source_pair.get(pair, 0) + 1
        
        return {
            "total_matches": total,
            "by_confidence": by_confidence,
            "by_match_type": by_type,
            "average_match_score": round(avg_score, 4),
            "by_source_pair": by_source_pair
        }
    
    def get_matches_by_confidence(
        self,
        confidence: MatchResolution,
        run_id: Optional[str] = None
    ) -> List[MatchRecord]:
        """Get matches filtered by confidence level."""
        records = self._match_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.resolution_confidence == confidence]
    
    def persist_records(self, run_id: str) -> Optional[Path]:
        """Persist match records for a run to disk."""
        if not self.log_dir:
            return None
        
        match_records = [r for r in self._match_records if r.run_id == run_id]
        batch_records = [r for r in self._batch_records if r.run_id == run_id]
        
        if not match_records and not batch_records:
            return None
        
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            run_dir = self.log_dir / "matches" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{run_id}_matches.json"
            with open(file_path, "w") as f:
                json.dump({
                    "run_id": run_id,
                    "matches": [r.to_dict() for r in match_records],
                    "batches": [r.to_dict() for r in batch_records],
                    "summary": self.get_match_summary(run_id)
                }, f, indent=2)
            
            return file_path
        except Exception as e:
            self.logger.error(
                "failed_to_persist_match_records",
                run_id=run_id,
                error=str(e)
            )
            return None
    
    def clear_records(self, run_id: Optional[str] = None) -> None:
        """Clear stored records."""
        if run_id:
            self._match_records = [r for r in self._match_records if r.run_id != run_id]
            self._batch_records = [r for r in self._batch_records if r.run_id != run_id]
        else:
            self._match_records.clear()
            self._batch_records.clear()


# Singleton instance
_match_logger_instance: Optional[MatchLogger] = None


def initialize_match_logger(log_dir: Optional[Path] = None) -> MatchLogger:
    """Initialize the global match logger instance."""
    global _match_logger_instance
    _match_logger_instance = MatchLogger(log_dir=log_dir)
    return _match_logger_instance


def get_match_logger() -> MatchLogger:
    """Get the global match logger instance."""
    if _match_logger_instance is None:
        return MatchLogger()
    return _match_logger_instance
