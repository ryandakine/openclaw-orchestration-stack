"""
Main scheduler and runner for the Sportsbook/Arbitrage Hunter.

Orchestrates the full pipeline:
    [Scheduled Trigger] → [Fetch Sportsbook Data] → [Fetch Prediction Market Data]
    → [Normalize Data] → [Save to DB] → [Run Arbitrage Detection] → [Send Telegram Alerts]

Runs continuously as a service with graceful shutdown handling.
"""

import asyncio
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.config import Config, ConfigLoader
from src.utils.logger import get_logger


# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_SHUTDOWN = 130  # Ctrl+C


@dataclass
class PipelineResult:
    """Result of a complete pipeline run."""
    run_id: str
    start_time: datetime
    end_time: datetime | None = None
    success: bool = False
    stage_results: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    arbitrages_found: int = 0
    alerts_sent: int = 0
    
    def __post_init__(self):
        if not self.run_id:
            self.run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    
    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()
    
    def add_error(self, stage: str, error: Exception, context: dict | None = None):
        """Record an error that occurred during pipeline execution."""
        self.errors.append({
            "stage": stage,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "context": context or {},
        })
        self.success = False
    
    def add_stage_result(self, stage: str, result: Any):
        """Record the result of a pipeline stage."""
        self.stage_results[stage] = result


class ArbitrageRunner:
    """
    Main runner class that orchestrates the arbitrage hunting pipeline.
    
    Runs continuously on a schedule, handling:
    - Data fetching from sportsbooks and prediction markets
    - Data normalization and storage
    - Arbitrage detection
    - Alert dispatching
    - Graceful shutdown
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(__name__).bind(component="runner")
        self._shutdown_event = asyncio.Event()
        self._running = False
        self._current_task: asyncio.Task | None = None
        self._run_count = 0
        self._last_run_result: PipelineResult | None = None
    
    def _generate_run_id(self) -> str:
        """Generate a unique run ID."""
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    
    async def fetch_sportsbook_data(
        self,
        run_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch data from all configured sportsbooks.
        
        Returns:
            Dictionary mapping source name to list of markets
        """
        log = self.logger.bind(run_id=run_id, stage="fetch_sportsbooks")
        log.info("fetching_sportsbook_data")
        
        results: dict[str, list[dict[str, Any]]] = {}
        sportsbooks = self.config.get_enabled_sportsbooks()
        
        if not sportsbooks:
            log.warning("no_sportsbooks_enabled")
            return results
        
        # Fetch from each sportsbook concurrently
        tasks = []
        for source_name, source_config in sportsbooks.items():
            if not self.config.is_source_configured(source_name):
                log.warning("sportsbook_not_configured", source=source_name)
                continue
            # Create fetch task for this sportsbook
            task = self._fetch_single_source(source_name, source_config, run_id)
            tasks.append(task)
        
        # Wait for all fetches with timeout
        try:
            fetch_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.fetch_timeout_seconds * len(tasks),
            )
            
            for source_name, result in zip(sportsbooks.keys(), fetch_results):
                if isinstance(result, Exception):
                    log.error("sportsbook_fetch_failed", source=source_name, error=str(result))
                    results[source_name] = []
                else:
                    results[source_name] = result
                    log.info("sportsbook_fetch_complete", source=source_name, markets=len(result))
                    
        except asyncio.TimeoutError:
            log.error("sportsbook_fetch_timeout")
        
        total_markets = sum(len(m) for m in results.values())
        log.info("sportsbook_fetch_all_complete", total_markets=total_markets)
        return results
    
    async def fetch_prediction_market_data(
        self,
        run_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch data from all configured prediction markets.
        
        Returns:
            Dictionary mapping source name to list of markets
        """
        log = self.logger.bind(run_id=run_id, stage="fetch_prediction_markets")
        log.info("fetching_prediction_market_data")
        
        results: dict[str, list[dict[str, Any]]] = {}
        markets = self.config.get_enabled_prediction_markets()
        
        if not markets:
            log.warning("no_prediction_markets_enabled")
            return results
        
        tasks = []
        for source_name, source_config in markets.items():
            task = self._fetch_single_source(source_name, source_config, run_id)
            tasks.append((source_name, task))
        
        for source_name, task in tasks:
            try:
                result = await asyncio.wait_for(
                    task,
                    timeout=self.config.fetch_timeout_seconds,
                )
                results[source_name] = result
                log.info("prediction_market_fetch_complete", source=source_name, markets=len(result))
            except asyncio.TimeoutError:
                log.error("prediction_market_fetch_timeout", source=source_name)
                results[source_name] = []
            except Exception as e:
                log.error("prediction_market_fetch_failed", source=source_name, error=str(e))
                results[source_name] = []
        
        total_markets = sum(len(m) for m in results.values())
        log.info("prediction_market_fetch_all_complete", total_markets=total_markets)
        return results
    
    async def _fetch_single_source(
        self,
        name: str,
        source_config: Any,
        run_id: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch data from a single source.
        
        This is a placeholder implementation. In production, this would:
        - Make actual HTTP requests to the source API
        - Handle authentication
        - Parse and validate responses
        - Implement retry logic
        """
        log = self.logger.bind(run_id=run_id, source_name=name)
        log.debug("fetching_single_source", url=source_config.api_url)
        
        # Simulate API call delay
        await asyncio.sleep(0.1)
        
        # Placeholder: Return mock data structure
        # In production, this would make actual API calls
        return []
    
    async def normalize_data(
        self,
        sportsbook_data: dict[str, list[dict[str, Any]]],
        prediction_market_data: dict[str, list[dict[str, Any]]],
        run_id: str,
    ) -> list[dict[str, Any]]:
        """
        Normalize data from all sources into a common format.
        
        Args:
            sportsbook_data: Raw data from sportsbooks
            prediction_market_data: Raw data from prediction markets
            run_id: Current run ID
        
        Returns:
            List of normalized market objects
        """
        log = self.logger.bind(run_id=run_id, stage="normalize")
        log.info("normalizing_data")
        
        normalized = []
        
        # Normalize sportsbook data
        for source, markets in sportsbook_data.items():
            for market in markets:
                normalized_market = {
                    "id": f"{source}_{market.get('id', '')}",
                    "source": source,
                    "source_type": "sportsbook",
                    "event_title": market.get("event_title", ""),
                    "sport": market.get("sport", ""),
                    "market_type": market.get("market_type", ""),
                    "outcomes": market.get("outcomes", []),
                    "start_time": market.get("start_time"),
                    "normalized_at": datetime.utcnow().isoformat(),
                    "run_id": run_id,
                }
                normalized.append(normalized_market)
        
        # Normalize prediction market data
        for source, markets in prediction_market_data.items():
            for market in markets:
                normalized_market = {
                    "id": f"{source}_{market.get('id', '')}",
                    "source": source,
                    "source_type": "prediction_market",
                    "event_title": market.get("question", ""),
                    "sport": market.get("category", ""),
                    "market_type": "moneyline",  # Default for prediction markets
                    "outcomes": [
                        {
                            "name": o.get("name", ""),
                            "probability": o.get("probability", 0),
                            "price": o.get("price", 0),
                        }
                        for o in market.get("outcomes", [])
                    ],
                    "end_date": market.get("end_date"),
                    "normalized_at": datetime.utcnow().isoformat(),
                    "run_id": run_id,
                }
                normalized.append(normalized_market)
        
        log.info("normalization_complete", normalized_count=len(normalized))
        return normalized
    
    async def save_to_database(
        self,
        normalized_data: list[dict[str, Any]],
        run_id: str,
    ) -> dict[str, Any]:
        """
        Save normalized data to the database.
        
        Args:
            normalized_data: List of normalized market objects
            run_id: Current run ID
        
        Returns:
            Result summary (records saved, errors, etc.)
        """
        log = self.logger.bind(run_id=run_id, stage="save_to_db")
        log.info("saving_to_database", records=len(normalized_data))
        
        if not self.config.database.enabled:
            log.info("database_disabled")
            return {"saved": 0, "skipped": len(normalized_data)}
        
        # Placeholder: In production, this would:
        # - Connect to PostgreSQL
        # - Insert/update market data
        # - Handle duplicates
        # - Update timestamps
        
        # Simulate database operation
        await asyncio.sleep(0.05)
        
        result = {
            "saved": len(normalized_data),
            "updated": 0,
            "errors": 0,
            "duration_ms": 50,
        }
        
        log.info("database_save_complete", **result)
        return result
    
    async def run_arbitrage_detection(
        self,
        normalized_data: list[dict[str, Any]],
        run_id: str,
    ) -> list[dict[str, Any]]:
        """
        Run arbitrage detection on normalized data.
        
        Args:
            normalized_data: List of normalized market objects
            run_id: Current run ID
        
        Returns:
            List of detected arbitrage opportunities
        """
        log = self.logger.bind(run_id=run_id, stage="arbitrage_detection")
        log.info("running_arbitrage_detection", markets=len(normalized_data))
        
        arbitrages = []
        
        # Group markets by event to find cross-market opportunities
        events: dict[str, list[dict[str, Any]]] = {}
        for market in normalized_data:
            event_key = market.get("event_title", "").lower().strip()
            if event_key:
                events.setdefault(event_key, []).append(market)
        
        # Look for arbitrage opportunities within each event
        for event_key, event_markets in events.items():
            # Need at least one sportsbook and one prediction market
            sportsbook_markets = [m for m in event_markets if m.get("source_type") == "sportsbook"]
            pm_markets = [m for m in event_markets if m.get("source_type") == "prediction_market"]
            
            for sb_market in sportsbook_markets:
                for pm_market in pm_markets:
                    # Compare outcomes and calculate arbitrage
                    arb = self._calculate_arbitrage(sb_market, pm_market)
                    if arb and arb.get("profit_percent", 0) >= self.config.min_profit_threshold:
                        arbitrages.append(arb)
        
        # Sort by profit percentage
        arbitrages.sort(key=lambda x: x.get("profit_percent", 0), reverse=True)
        
        log.info(
            "arbitrage_detection_complete",
            opportunities=len(arbitrages),
            threshold=self.config.min_profit_threshold,
        )
        return arbitrages
    
    def _calculate_arbitrage(
        self,
        sportsbook_market: dict[str, Any],
        prediction_market: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Calculate if there's an arbitrage opportunity between two markets.
        
        Args:
            sportsbook_market: Normalized sportsbook market
            prediction_market: Normalized prediction market
        
        Returns:
            Arbitrage opportunity dict or None if no arb exists
        """
        # Placeholder implementation
        # In production, this would:
        # - Match outcomes between markets
        # - Calculate implied probabilities
        # - Check for arbitrage conditions
        # - Account for fees and slippage
        return None
    
    async def send_telegram_alerts(
        self,
        arbitrages: list[dict[str, Any]],
        run_id: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send Telegram alerts for detected arbitrages.
        
        Args:
            arbitrages: List of arbitrage opportunities
            run_id: Current run ID
            dry_run: If True, don't actually send alerts
        
        Returns:
            Alert result summary
        """
        log = self.logger.bind(run_id=run_id, stage="send_alerts")
        log.info("sending_telegram_alerts", count=len(arbitrages), dry_run=dry_run)
        
        if not self.config.telegram_enabled:
            log.info("telegram_disabled")
            return {"sent": 0, "reason": "disabled"}
        
        if not arbitrages:
            log.info("no_arbitrages_to_alert")
            return {"sent": 0, "reason": "no_arbitrages"}
        
        if dry_run:
            log.info("dry_run_alert", would_send=len(arbitrages))
            return {"sent": 0, "reason": "dry_run", "would_send": len(arbitrages)}
        
        # Placeholder: In production, this would:
        # - Format messages using telegram_formatter style
        # - Send via Telegram Bot API
        # - Handle rate limiting
        # - Track delivery status
        
        # Take top N alerts
        top_arbitrages = arbitrages[:self.config.top_n_alerts]
        
        result = {
            "sent": len(top_arbitrages),
            "failed": 0,
            "total": len(arbitrages),
        }
        
        log.info("telegram_alerts_sent", **result)
        return result
    
    async def run_single_scan(
        self,
        run_id: str | None = None,
        dry_run: bool = False,
    ) -> PipelineResult:
        """
        Run a single complete scan of the arbitrage pipeline.
        
        Args:
            run_id: Optional run ID (generated if not provided)
            dry_run: If True, don't actually send alerts
        
        Returns:
            PipelineResult with full execution details
        """
        run_id = run_id or self._generate_run_id()
        result = PipelineResult(run_id=run_id, start_time=datetime.utcnow())
        
        log = self.logger.bind(run_id=run_id)
        log.info("pipeline_started", dry_run=dry_run)
        
        try:
            # Stage 1: Fetch sportsbook data
            log.info("stage_1_fetch_sportsbooks")
            sportsbook_data = await self.fetch_sportsbook_data(run_id)
            result.add_stage_result("fetch_sportsbooks", {
                "sources": list(sportsbook_data.keys()),
                "total_markets": sum(len(m) for m in sportsbook_data.values()),
            })
            
            # Stage 2: Fetch prediction market data
            log.info("stage_2_fetch_prediction_markets")
            prediction_market_data = await self.fetch_prediction_market_data(run_id)
            result.add_stage_result("fetch_prediction_markets", {
                "sources": list(prediction_market_data.keys()),
                "total_markets": sum(len(m) for m in prediction_market_data.values()),
            })
            
            # Stage 3: Normalize data
            log.info("stage_3_normalize")
            normalized_data = await self.normalize_data(
                sportsbook_data,
                prediction_market_data,
                run_id,
            )
            result.add_stage_result("normalize", {
                "normalized_count": len(normalized_data),
            })
            
            # Stage 4: Save to database
            log.info("stage_4_save_to_db")
            db_result = await self.save_to_database(normalized_data, run_id)
            result.add_stage_result("save_to_db", db_result)
            
            # Stage 5: Run arbitrage detection
            log.info("stage_5_arbitrage_detection")
            arbitrages = await self.run_arbitrage_detection(normalized_data, run_id)
            result.arbitrages_found = len(arbitrages)
            result.add_stage_result("arbitrage_detection", {
                "opportunities_found": len(arbitrages),
                "top_profit": arbitrages[0].get("profit_percent") if arbitrages else None,
            })
            
            # Stage 6: Send alerts
            log.info("stage_6_send_alerts")
            alert_result = await self.send_telegram_alerts(arbitrages, run_id, dry_run)
            result.alerts_sent = alert_result.get("sent", 0)
            result.add_stage_result("send_alerts", alert_result)
            
            result.success = True
            result.end_time = datetime.utcnow()
            
            log.info(
                "pipeline_complete",
                duration_seconds=result.duration_seconds,
                arbitrages_found=result.arbitrages_found,
                alerts_sent=result.alerts_sent,
            )
            
        except Exception as e:
            result.end_time = datetime.utcnow()
            result.add_error("pipeline", e)
            log.error(
                "pipeline_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=result.duration_seconds,
            )
            raise  # Re-raise to let caller handle
        
        return result
    
    async def run_scheduled(self) -> None:
        """
        Run the pipeline continuously on a schedule.
        
        Runs until shutdown_event is set (via Ctrl+C or signal).
        """
        log = self.logger.bind(component="scheduler")
        log.info(
            "scheduler_started",
            interval_minutes=self.config.scan_interval_minutes,
            enabled=self.config.enabled,
        )
        
        if not self.config.enabled:
            log.warning("runner_disabled_by_config")
            return
        
        self._running = True
        
        while not self._shutdown_event.is_set():
            self._run_count += 1
            run_id = self._generate_run_id()
            
            log.info(
                "scheduled_run_starting",
                run_number=self._run_count,
                run_id=run_id,
            )
            
            try:
                result = await self.run_single_scan(run_id=run_id)
                self._last_run_result = result
                
                log.info(
                    "scheduled_run_complete",
                    run_number=self._run_count,
                    success=result.success,
                    duration_seconds=result.duration_seconds,
                    arbitrages_found=result.arbitrages_found,
                )
                
            except Exception as e:
                log.error(
                    "scheduled_run_failed",
                    run_number=self._run_count,
                    error=str(e),
                )
                # Continue to next iteration - don't crash on single failure
            
            # Wait for next scan interval or shutdown
            try:
                wait_seconds = self.config.scan_interval_minutes * 60
                log.info("waiting_for_next_scan", seconds=wait_seconds)
                
                # Wait with early exit on shutdown
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=wait_seconds,
                )
            except asyncio.TimeoutError:
                # Normal timeout - continue to next scan
                pass
        
        self._running = False
        log.info("scheduler_stopped", total_runs=self._run_count)
    
    async def run_once(self, dry_run: bool = False) -> PipelineResult:
        """
        Run the pipeline once (useful for testing or manual execution).
        
        Args:
            dry_run: If True, don't actually send alerts
        
        Returns:
            PipelineResult with full execution details
        """
        return await self.run_single_scan(dry_run=dry_run)
    
    def shutdown(self) -> None:
        """Signal the runner to shutdown gracefully."""
        self.logger.info("shutdown_requested")
        self._shutdown_event.set()
    
    @property
    def is_running(self) -> bool:
        """Check if the runner is currently running."""
        return self._running
    
    @property
    def run_count(self) -> int:
        """Get the number of completed runs."""
        return self._run_count
    
    @property
    def last_run_result(self) -> PipelineResult | None:
        """Get the result of the most recent run."""
        return self._last_run_result


async def create_runner(config_path: str | None = None) -> ArbitrageRunner:
    """
    Factory function to create and configure an ArbitrageRunner.
    
    Args:
        config_path: Optional path to config file
    
    Returns:
        Configured ArbitrageRunner instance
    """
    logger = get_logger(__name__)
    logger.info("creating_runner", config_path=config_path)
    
    # Load configuration
    config = ConfigLoader.load(config_path)
    
    # Validate configuration
    is_valid, errors = ConfigLoader.validate(config)
    if not is_valid:
        raise ValueError(f"Invalid configuration: {'; '.join(errors)}")
    
    logger.info("configuration_loaded", sources=list(config.get_enabled_sources().keys()))
    
    return ArbitrageRunner(config)
