
"""
Match Rejection Logger - Log why matches were rejected for tuning.

Module 2.10: Comprehensive logging of rejected matches to enable
continuous improvement of matching algorithms and threshold tuning.
"""

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from match_result_schema import MatchResult, MatchStatus, RejectionReason


class LogLevel(str, Enum):
    """Log levels for rejection logging."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class RejectionLogEntry:
    """A single rejection log entry."""
    timestamp: str
    match_id: str
    left_source: str
    left_event_id: str
    left_event_title: str
    right_source: str
    right_event_id: str
    right_event_title: str
    rejection_reason: str
    rejection_details: str
    match_score: float
    title_similarity: float
    entity_match: float
    date_match: float
    category_match: float
    category_left: str
    category_right: str
    left_entities: dict[str, list[str]]
    right_entities: dict[str, list[str]]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class MatchRejectionLogger:
    """Logs rejected matches for analysis and algorithm tuning."""
    
    def __init__(
        self,
        log_dir: Optional[str] = None,
        log_level: LogLevel = LogLevel.INFO,
    ) -> None:
        self.log_dir = Path(log_dir or os.getenv(
            "OPENCLAW_REJECTION_LOG_DIR",
            "/tmp/openclaw/rejections"
        ))
        self.log_level = log_level
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.stats: dict[str, Any] = {
            "total_logged": 0,
            "by_reason": {},
            "by_category_pair": {},
            "score_distribution": {
                "0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0,
                "0.6-0.8": 0, "0.8-1.0": 0,
            },
        }
        self._current_date: Optional[str] = None
        self._current_file: Optional[Path] = None
        self._lock = asyncio.Lock()
    
    async def log_rejection(self, match_result: MatchResult) -> None:
        """Log a rejected match."""
        if match_result.status != MatchStatus.REJECTED:
            return
        entry = self._create_entry(match_result)
        self._update_stats(entry)
        await self._write_entry(entry)
    
    async def log_batch(self, match_results: list[MatchResult]) -> dict[str, int]:
        """Log a batch of rejected matches."""
        counts: dict[str, int] = {}
        for result in match_results:
            if result.status == MatchStatus.REJECTED:
                await self.log_rejection(result)
                reason = result.rejection_reason.value
                counts[reason] = counts.get(reason, 0) + 1
        return counts
    
    def _create_entry(self, match_result: MatchResult) -> RejectionLogEntry:
        """Create a log entry from a match result."""
        return RejectionLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            match_id=match_result.match_id,
            left_source=match_result.left_source,
            left_event_id=match_result.left_event_id,
            left_event_title=match_result.left_event_title,
            right_source=match_result.right_source,
            right_event_id=match_result.right_event_id,
            right_event_title=match_result.right_event_title,
            rejection_reason=match_result.rejection_reason.value,
            rejection_details=match_result.rejection_details,
            match_score=match_result.match_score,
            title_similarity=match_result.scores.title_similarity,
            entity_match=match_result.scores.entity_match,
            date_match=match_result.scores.date_match,
            category_match=match_result.scores.category_match,
            category_left=match_result.left_category,
            category_right=match_result.right_category,
            left_entities=match_result.left_entities.to_dict(),
            right_entities=match_result.right_entities.to_dict(),
        )
    
    def _update_stats(self, entry: RejectionLogEntry) -> None:
        """Update rejection statistics."""
        self.stats["total_logged"] += 1
        reason = entry.rejection_reason
        self.stats["by_reason"][reason] = self.stats["by_reason"].get(reason, 0) + 1
        cat_pair = f"{entry.category_left}:{entry.category_right}"
        self.stats["by_category_pair"][cat_pair] = (
            self.stats["by_category_pair"].get(cat_pair, 0) + 1
        )
        score = entry.match_score
        if score < 0.2:
            self.stats["score_distribution"]["0.0-0.2"] += 1
        elif score < 0.4:
            self.stats["score_distribution"]["0.2-0.4"] += 1
        elif score < 0.6:
            self.stats["score_distribution"]["0.4-0.6"] += 1
        elif score < 0.8:
            self.stats["score_distribution"]["0.6-0.8"] += 1
        else:
            self.stats["score_distribution"]["0.8-1.0"] += 1
    
    async def _write_entry(self, entry: RejectionLogEntry) -> None:
        """Write entry to log file."""
        async with self._lock:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            if self._current_date != today or self._current_file is None:
                self._current_date = today
                self._current_file = self.log_dir / f"rejections_{today}.jsonl"
            line = entry.to_json() + "\n"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._append_to_file, self._current_file, line)
    
    def _append_to_file(self, file_path: Path, content: str) -> None:
        """Append content to file."""
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content)
    
    def get_stats(self) -> dict[str, Any]:
        """Get current rejection statistics."""
        return self.stats.copy()
    
    def get_rejection_report(self, days: int = 7) -> dict[str, Any]:
        """Generate a rejection report for the last N days."""
        return {
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": self.stats.copy(),
            "top_rejection_reasons": sorted(
                self.stats["by_reason"].items(), key=lambda x: x[1], reverse=True
            )[:10],
            "top_category_mismatches": sorted(
                self.stats["by_category_pair"].items(), key=lambda x: x[1], reverse=True
            )[:10],
        }
    
    def reset_stats(self) -> None:
        """Reset rejection statistics."""
        self.stats = {
            "total_logged": 0,
            "by_reason": {},
            "by_category_pair": {},
            "score_distribution": {
                "0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0,
                "0.6-0.8": 0, "0.8-1.0": 0,
            },
        }


_default_logger: Optional[MatchRejectionLogger] = None


def get_rejection_logger() -> MatchRejectionLogger:
    """Get the default rejection logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = MatchRejectionLogger()
    return _default_logger


async def log_match_rejection(match_result: MatchResult) -> None:
    """Convenience function to log a rejected match."""
    await get_rejection_logger().log_rejection(match_result)
