"""
Audit logger module.

Writes complete audit trail: markets fetched, matches, rejects, alerts sent.
"""

import json
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from enum import Enum

import aiofiles
import structlog

from .config_loader import Config
from .job_context import JobContext
from .fetch_all_sources import FetchResult
from .normalize_all import NormalizeResult
from .match_all import MatchResult, MarketMatch
from .calculate_all_arbs import ArbCalculationResult, ArbOpportunity, ArbStatus
from .filter_and_rank import FilterResult, ArbAlert
from .send_alerts import AlertResult

logger = structlog.get_logger(__name__)


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime and other non-serializable types."""
    
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return super().default(obj)


@dataclass
class AuditRecord:
    """Complete audit record for a single run."""
    
    # Run identification
    run_id: str
    correlation_id: str
    started_at: str
    completed_at: str
    duration_seconds: float
    
    # Environment
    version: str
    hostname: str
    python_version: str
    
    # Configuration (sanitized - no API keys)
    config_summary: dict[str, Any]
    
    # Pipeline results
    fetch_results: list[dict[str, Any]]
    normalize_results: list[dict[str, Any]]
    match_result: dict[str, Any]
    calculation_result: dict[str, Any]
    filter_result: dict[str, Any]
    alert_result: dict[str, Any]
    
    # Final metrics
    metrics: dict[str, int]
    
    # Errors and warnings
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    
    # Status
    success: bool
    exit_code: int


class AuditLogger:
    """Handles writing complete audit trails to disk."""
    
    def __init__(self, config: Config, ctx: JobContext):
        self.config = config
        self.ctx = ctx
        self.log = logger.bind(run_id=ctx.run_id)
        
        # Ensure audit log directory exists
        self.audit_dir = config.audit_log_path
        self.log.debug("audit_logger_initialized", audit_dir=str(self.audit_dir))
    
    async def _ensure_directory(self) -> None:
        """Ensure the audit log directory exists."""
        if not self.audit_dir.exists():
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            self.log.debug("created_audit_directory", path=str(self.audit_dir))
    
    def _sanitize_config(self) -> dict[str, Any]:
        """Create a sanitized version of config for logging (no secrets)."""
        return {
            "enabled": self.config.enabled,
            "min_edge_percent": self.config.min_edge_percent,
            "min_profit_per_unit": self.config.min_profit_per_unit,
            "max_stake_per_leg": self.config.max_stake_per_leg,
            "max_total_exposure": self.config.max_total_exposure,
            "top_n_alerts": self.config.top_n_alerts,
            "enable_audit_logging": self.config.enable_audit_logging,
            "fetch_timeout_seconds": self.config.fetch_timeout_seconds,
            "total_scan_timeout_seconds": self.config.total_scan_timeout_seconds,
            "max_concurrent_requests": self.config.max_concurrent_requests,
            "has_polymarket_key": self.config.polymarket_api_key is not None,
            "enabled_sportsbooks": self.config.get_enabled_sportsbooks(),
            "has_telegram_config": (
                self.config.telegram_bot_token is not None and 
                self.config.telegram_chat_id is not None
            ),
        }
    
    def _serialize_fetch_results(self, fetch_results: list[FetchResult]) -> list[dict[str, Any]]:
        """Serialize fetch results for audit."""
        return [
            {
                "source": r.source,
                "success": r.success,
                "market_count": r.market_count,
                "duration_seconds": round(r.duration_seconds, 3),
                "error": str(r.error) if r.error else None,
            }
            for r in fetch_results
        ]
    
    def _serialize_normalize_results(
        self, 
        normalize_results: list[NormalizeResult]
    ) -> list[dict[str, Any]]:
        """Serialize normalization results for audit."""
        return [
            {
                "source": r.source,
                "success": r.success,
                "normalized_count": len(r.normalized),
                "rejected_count": len(r.rejected),
                "error": str(r.error) if r.error else None,
            }
            for r in normalize_results
        ]
    
    def _serialize_match_result(self, match_result: MatchResult) -> dict[str, Any]:
        """Serialize match result for audit."""
        return {
            "total_matches": match_result.total_matches,
            "matches_by_sportsbook": self._count_matches_by_sportsbook(match_result.matches),
            "rejects_count": len(match_result.rejects),
            "sample_matches": [
                {
                    "match_id": m.match_id,
                    "sportsbook": m.sportsbook,
                    "event_title": m.polymarket_market.event_title[:50],
                    "match_score": round(m.match_score, 3),
                }
                for m in match_result.matches[:5]  # Sample first 5
            ],
        }
    
    def _count_matches_by_sportsbook(self, matches: list[MarketMatch]) -> dict[str, int]:
        """Count matches by sportsbook."""
        counts: dict[str, int] = {}
        for m in matches:
            counts[m.sportsbook] = counts.get(m.sportsbook, 0) + 1
        return counts
    
    def _serialize_calculation_result(
        self, 
        calc_result: ArbCalculationResult
    ) -> dict[str, Any]:
        """Serialize calculation results for audit."""
        status_counts: dict[str, int] = {}
        for arb in calc_result.valid_arbs:
            status = arb.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_calculated": calc_result.total_calculated,
            "valid_arbs": len(calc_result.valid_arbs),
            "rejected": len(calc_result.rejected),
            "status_breakdown": status_counts,
            "top_arbs": [
                {
                    "arb_id": a.arb_id,
                    "sportsbook": a.sportsbook,
                    "edge_percent": round(a.edge_percent, 2),
                    "guaranteed_profit": round(a.guaranteed_profit, 2),
                    "event": a.event_title[:40],
                }
                for a in sorted(calc_result.valid_arbs, key=lambda x: x.edge_percent, reverse=True)[:5]
            ],
        }
    
    def _serialize_filter_result(self, filter_result: FilterResult) -> dict[str, Any]:
        """Serialize filter results for audit."""
        priority_counts: dict[str, int] = {}
        for alert in filter_result.alerts:
            priority_counts[alert.alert_priority] = priority_counts.get(alert.alert_priority, 0) + 1
        
        return {
            "total_filtered": filter_result.total_filtered,
            "alerts_generated": len(filter_result.alerts),
            "filtered_out": len(filter_result.filtered_out),
            "priority_breakdown": priority_counts,
            "top_alerts": [
                {
                    "rank": a.rank,
                    "priority": a.alert_priority,
                    "edge": round(a.arb.edge_percent, 2),
                    "profit": round(a.arb.guaranteed_profit, 2),
                }
                for a in filter_result.alerts[:5]
            ],
        }
    
    def _serialize_alert_result(self, alert_result: AlertResult) -> dict[str, Any]:
        """Serialize alert results for audit."""
        return {
            "total_attempted": alert_result.total_attempted,
            "sent_count": alert_result.sent_count,
            "failed_count": alert_result.failed_count,
            "errors": alert_result.errors,
        }
    
    async def write_audit_log(
        self,
        fetch_results: list[FetchResult],
        normalize_results: list[NormalizeResult],
        match_result: MatchResult,
        calculation_result: ArbCalculationResult,
        filter_result: FilterResult,
        alert_result: AlertResult,
        success: bool,
        exit_code: int,
    ) -> Path:
        """
        Write complete audit log to disk.
        
        Returns the path to the written audit file.
        """
        await self._ensure_directory()
        
        completed_at = datetime.utcnow()
        duration = self.ctx.duration_seconds
        
        record = AuditRecord(
            run_id=self.ctx.run_id,
            correlation_id=self.ctx.correlation_id,
            started_at=self.ctx.started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=round(duration, 3),
            version=self.ctx.version,
            hostname=self.ctx.hostname,
            python_version=self.ctx.python_version,
            config_summary=self._sanitize_config(),
            fetch_results=self._serialize_fetch_results(fetch_results),
            normalize_results=self._serialize_normalize_results(normalize_results),
            match_result=self._serialize_match_result(match_result),
            calculation_result=self._serialize_calculation_result(calculation_result),
            filter_result=self._serialize_filter_result(filter_result),
            alert_result=self._serialize_alert_result(alert_result),
            metrics={
                "markets_fetched": self.ctx.markets_fetched,
                "markets_normalized": self.ctx.markets_normalized,
                "matches_found": self.ctx.matches_found,
                "arbs_calculated": self.ctx.arbs_calculated,
                "arbs_filtered": self.ctx.arbs_filtered,
                "alerts_sent": self.ctx.alerts_sent,
            },
            errors=self.ctx.errors,
            warnings=self.ctx.warnings,
            success=success,
            exit_code=exit_code,
        )
        
        # Generate filename
        timestamp = self.ctx.started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"audit_{timestamp}_{self.ctx.run_id}.json"
        filepath = self.audit_dir / filename
        
        # Write to file
        try:
            async with aiofiles.open(filepath, 'w') as f:
                json_data = json.dumps(asdict(record), cls=JSONEncoder, indent=2)
                await f.write(json_data)
            
            self.log.info(
                "audit_log_written",
                filepath=str(filepath),
                size_bytes=len(json_data),
            )
            
            return filepath
            
        except Exception as e:
            self.log.error("audit_log_write_failed", error=str(e), filepath=str(filepath))
            raise
    
    async def write_markets_debug(
        self,
        markets: list[dict[str, Any]],
        stage: str,
    ) -> Path | None:
        """
        Write debug dump of markets at a specific pipeline stage.
        
        Returns path to written file or None if disabled.
        """
        if not self.config.enable_audit_logging:
            return None
        
        await self._ensure_directory()
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_{stage}_{timestamp}_{self.ctx.run_id}.json"
        filepath = self.audit_dir / "debug" / filename
        
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(filepath, 'w') as f:
                json_data = json.dumps({
                    "run_id": self.ctx.run_id,
                    "stage": stage,
                    "timestamp": datetime.utcnow().isoformat(),
                    "market_count": len(markets),
                    "markets": markets[:100],  # Limit to first 100 for size
                }, cls=JSONEncoder, indent=2)
                await f.write(json_data)
            
            self.log.debug("debug_markets_written", filepath=str(filepath), count=len(markets))
            return filepath
            
        except Exception as e:
            self.log.warning("debug_write_failed", error=str(e))
            return None


async def log_audit_trail(
    ctx: JobContext,
    config: Config,
    fetch_results: list[FetchResult],
    normalize_results: list[NormalizeResult],
    match_result: MatchResult,
    calculation_result: ArbCalculationResult,
    filter_result: FilterResult,
    alert_result: AlertResult,
    success: bool,
    exit_code: int,
) -> Path:
    """
    Convenience function to write complete audit trail.
    
    Returns path to written audit file.
    """
    logger.info("writing_audit_trail", run_id=ctx.run_id)
    
    audit_logger = AuditLogger(config, ctx)
    
    filepath = await audit_logger.write_audit_log(
        fetch_results=fetch_results,
        normalize_results=normalize_results,
        match_result=match_result,
        calculation_result=calculation_result,
        filter_result=filter_result,
        alert_result=alert_result,
        success=success,
        exit_code=exit_code,
    )
    
    logger.info("audit_trail_complete", filepath=str(filepath))
    return filepath
