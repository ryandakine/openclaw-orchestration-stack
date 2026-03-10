"""
Main runner module.

Main entry point for the arb hunter. Handles orchestration,
exception handling, and exit codes.
"""

import asyncio
import sys
import signal
from pathlib import Path
from typing import NoReturn

import structlog

from .config_loader import Config, ConfigLoader
from .job_context import JobContext, create_job_context
from .fetch_all_sources import fetch_all_sources
from .normalize_all import normalize_all
from .match_all import match_all
from .calculate_all_arbs import calculate_all_arbs
from .filter_and_rank import filter_and_rank
from .send_alerts import send_alerts
from .audit_logger import log_audit_trail

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NO_ARBS = 2

# Configure structlog
def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


class ArbHunterError(Exception):
    """Base exception for arb hunter errors."""
    pass


class ConfigurationError(ArbHunterError):
    """Raised when configuration is invalid."""
    pass


class PipelineError(ArbHunterError):
    """Raised when a pipeline stage fails."""
    pass


async def run_arb_hunt(
    config: Config | None = None,
    triggered_by: str = "manual",
) -> tuple[int, JobContext]:
    """
    Run the complete arbitrage hunting pipeline.
    
    Args:
        config: Configuration object (loads from env if None)
        triggered_by: What triggered this run (manual, cron, etc.)
    
    Returns:
        Tuple of (exit_code, final_context)
    """
    # Create job context
    ctx = create_job_context(triggered_by=triggered_by)
    log = logger.bind(run_id=ctx.run_id)
    
    log.info("arb_hunt_started")
    
    # Load config if not provided
    if config is None:
        try:
            config = ConfigLoader.from_env()
        except Exception as e:
            log.error("config_load_failed", error=str(e))
            return EXIT_ERROR, ctx.with_error(e, {"stage": "config_load"})
    
    # Validate config
    is_valid, errors = ConfigLoader.validate(config)
    if not is_valid:
        log.error("config_validation_failed", errors=errors)
        return EXIT_ERROR, ctx.with_error(
            ConfigurationError(f"Invalid config: {', '.join(errors)}"),
            {"errors": errors}
        )
    
    # Check if enabled
    if not config.enabled:
        log.info("arb_hunter_disabled")
        return EXIT_SUCCESS, ctx
    
    # Initialize result containers
    fetch_results = []
    normalize_results = []
    match_result = None
    calculation_result = None
    filter_result = None
    alert_result = None
    
    try:
        # Stage 1: Fetch all sources
        log.info("stage_fetch_starting")
        all_markets, ctx, fetch_results = await fetch_all_sources(config, ctx)
        ctx = ctx.with_stage_completed("fetch")
        log.info("stage_fetch_complete", market_count=len(all_markets))
        
        # Stage 2: Normalize all markets
        log.info("stage_normalize_starting")
        normalized_markets, ctx, normalize_results = await normalize_all(
            all_markets, config, ctx
        )
        ctx = ctx.with_stage_completed("normalize")
        log.info("stage_normalize_complete", normalized_count=len(normalized_markets))
        
        # Stage 3: Match markets
        log.info("stage_match_starting")
        matches, ctx, match_result = await match_all(normalized_markets, config, ctx)
        ctx = ctx.with_stage_completed("match")
        log.info("stage_match_complete", match_count=len(matches))
        
        # Stage 4: Calculate arbitrages
        log.info("stage_calculate_starting")
        arbs, ctx, calculation_result = await calculate_all_arbs(matches, config, ctx)
        ctx = ctx.with_stage_completed("calculate")
        log.info("stage_calculate_complete", arb_count=len(arbs))
        
        # Stage 5: Filter and rank
        log.info("stage_filter_starting")
        alerts, ctx, filter_result = await filter_and_rank(arbs, config, ctx)
        ctx = ctx.with_stage_completed("filter")
        log.info("stage_filter_complete", alert_count=len(alerts))
        
        # Stage 6: Send alerts
        log.info("stage_alert_starting")
        alert_result, ctx = await send_alerts(alerts, config, ctx)
        ctx = ctx.with_stage_completed("alert")
        log.info("stage_alert_complete", sent=alert_result.sent_count if alert_result else 0)
        
        # Determine exit code
        if not alerts:
            exit_code = EXIT_NO_ARBS
            log.info("arb_hunt_complete_no_arbs")
        else:
            exit_code = EXIT_SUCCESS
            log.info("arb_hunt_complete_success", alerts_found=len(alerts))
        
    except Exception as e:
        log.error("pipeline_error", error=str(e), error_type=type(e).__name__)
        ctx = ctx.with_error(e, {"stage": "pipeline"})
        exit_code = EXIT_ERROR
    
    # Write audit trail (best effort)
    try:
        await log_audit_trail(
            ctx=ctx,
            config=config,
            fetch_results=fetch_results,
            normalize_results=normalize_results,
            match_result=match_result or type('obj', (object,), {
                'total_matches': 0, 'matches': [], 'rejects': []
            })(),
            calculation_result=calculation_result or type('obj', (object,), {
                'total_calculated': 0, 'valid_arbs': [], 'rejected': []
            })(),
            filter_result=filter_result or type('obj', (object,), {
                'total_filtered': 0, 'alerts': [], 'filtered_out': []
            })(),
            alert_result=alert_result or type('obj', (object,), {
                'total_attempted': 0, 'sent_count': 0, 'failed_count': 0, 'errors': []
            })(),
            success=exit_code == EXIT_SUCCESS,
            exit_code=exit_code,
        )
    except Exception as e:
        log.error("audit_trail_failed", error=str(e))
    
    return exit_code, ctx


def main() -> int:
    """
    Main entry point.
    
    Returns exit code:
        0 = Success (arbs found and alerted)
        1 = Error (configuration or pipeline failure)
        2 = No arbs found (success, but no opportunities)
    """
    configure_logging()
    
    log = logger.bind(entry_point="main")
    log.info("openclaw_arb_hunter_starting", version="1.0.0")
    
    # Handle signals gracefully
    def signal_handler(sig, frame):
        log.warning("received_signal", signal=sig)
        sys.exit(EXIT_ERROR)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run the async pipeline
        exit_code, ctx = asyncio.run(run_arb_hunt())
        
        log.info(
            "openclaw_arb_hunter_finished",
            exit_code=exit_code,
            run_id=ctx.run_id,
            duration_seconds=round(ctx.duration_seconds, 2),
            stages_completed=ctx.stages_completed,
            stages_failed=ctx.stages_failed,
            has_errors=ctx.has_errors,
        )
        
        return exit_code
        
    except KeyboardInterrupt:
        log.warning("interrupted_by_user")
        return EXIT_ERROR
    except Exception as e:
        log.error("fatal_error", error=str(e), error_type=type(e).__name__)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
