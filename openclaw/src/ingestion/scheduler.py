"""
Ingestion scheduler for running data ingestion on a schedule.

Provides scheduled and manual ingestion capabilities with logging
and error handling.
"""

import os
import json
import time
import uuid
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

from .sportsbook_client import (
    SportsbookClient,
    create_sportsbook_client,
    MockSportsbookClient,
)
from .prediction_market_client import (
    PredictionMarketClient,
    create_prediction_market_client,
    MockPredictionMarketClient,
)
from .normalizer import DataNormalizer, NormalizedEvent, normalize_data
from ..database.connection import IngestionDatabase, get_db_connection, transaction
from ..database.models import Event, Odds

logger = logging.getLogger(__name__)


class IngestionJob:
    """Represents a single ingestion job configuration."""
    
    def __init__(
        self,
        name: str,
        client: Union[SportsbookClient, PredictionMarketClient],
        fetch_method: str = "fetch_odds",
        fetch_params: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ):
        self.name = name
        self.client = client
        self.fetch_method = fetch_method
        self.fetch_params = fetch_params or {}
        self.enabled = enabled
    
    def run(self) -> List[Dict[str, Any]]:
        """Execute the ingestion job and return raw data."""
        if not self.enabled:
            logger.info(f"Job {self.name} is disabled, skipping")
            return []
        
        method = getattr(self.client, self.fetch_method)
        return method(**self.fetch_params)


class IngestionScheduler:
    """
    Scheduler for running data ingestion jobs.
    
    Supports:
    - Running jobs immediately (manual trigger)
    - Running jobs on a schedule (interval-based)
    - Multiple concurrent jobs from different sources
    - Error handling and retry logic
    - Audit logging
    """
    
    def __init__(
        self,
        db: Optional[IngestionDatabase] = None,
        db_path: Optional[str] = None,
    ):
        self.db = db or IngestionDatabase(db_path or os.getenv("ARB_HUNTER_DB_PATH", "data/arb_hunter.db"))
        self.normalizer = DataNormalizer()
        self.jobs: List[IngestionJob] = []
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._interval_seconds: int = 3600  # Default 1 hour
        self._stop_event = threading.Event()
    
    def add_job(self, job: IngestionJob) -> "IngestionScheduler":
        """Add an ingestion job to the scheduler."""
        self.jobs.append(job)
        logger.info(f"Added ingestion job: {job.name}")
        return self
    
    def add_sportsbook_job(
        self,
        name: str,
        client_type: str = "mock",
        sport: str = "NBA",
        market_type: Optional[str] = None,
        enabled: bool = True,
        **kwargs
    ) -> "IngestionScheduler":
        """
        Add a sportsbook ingestion job.
        
        Args:
            name: Job name
            client_type: 'odds_api' or 'mock'
            sport: Sport to fetch
            market_type: Market type filter
            enabled: Whether job is enabled
            **kwargs: Additional fetch parameters (num_events, etc.)
        """
        client = create_sportsbook_client(client_type)
        
        fetch_params = {"sport": sport, "market_type": market_type}
        fetch_params.update(kwargs)  # Add any additional fetch params
        
        job = IngestionJob(
            name=name,
            client=client,
            fetch_method="fetch_odds",
            fetch_params=fetch_params,
            enabled=enabled,
        )
        return self.add_job(job)
    
    def add_prediction_market_job(
        self,
        name: str,
        client_type: str = "mock",
        category: str = "sports",
        enabled: bool = True,
        **kwargs
    ) -> "IngestionScheduler":
        """
        Add a prediction market ingestion job.
        
        Args:
            name: Job name
            client_type: 'polymarket', 'kalshi', or 'mock'
            category: Market category
            enabled: Whether job is enabled
            **kwargs: Additional fetch parameters (num_markets, etc.)
        """
        client = create_prediction_market_client(client_type)
        
        fetch_params = {"category": category}
        fetch_params.update(kwargs)  # Add any additional fetch params
        
        job = IngestionJob(
            name=name,
            client=client,
            fetch_method="fetch_markets",
            fetch_params=fetch_params,
            enabled=enabled,
        )
        return self.add_job(job)
    
    def run_job(
        self,
        job: IngestionJob,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a single ingestion job.
        
        Args:
            job: The job to run
            run_id: Optional run ID for tracking
            
        Returns:
            Dict with job results and metadata
        """
        run_id = run_id or str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        result = {
            "run_id": run_id,
            "job_name": job.name,
            "start_time": start_time.isoformat(),
            "status": "running",
            "events_fetched": 0,
            "events_normalized": 0,
            "events_stored": 0,
            "errors": [],
        }
        
        logger.info(f"Starting ingestion job: {job.name} (run_id: {run_id})")
        
        try:
            # 1. Fetch raw data
            raw_data = job.run()
            result["events_fetched"] = len(raw_data)
            logger.info(f"Fetched {len(raw_data)} raw events from {job.name}")
            
            if not raw_data:
                result["status"] = "success"
                result["end_time"] = datetime.utcnow().isoformat()
                return result
            
            # 2. Normalize data
            normalized_events = self.normalizer.normalize(raw_data)
            result["events_normalized"] = len(normalized_events)
            logger.info(f"Normalized {len(normalized_events)} events")
            
            # 3. Store in database
            stored_count = 0
            for event in normalized_events:
                try:
                    self._store_event(event)
                    stored_count += 1
                except Exception as e:
                    error_msg = f"Failed to store event {event.event_id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
            
            result["events_stored"] = stored_count
            result["status"] = "success" if not result["errors"] else "partial"
            
            logger.info(
                f"Completed job {job.name}: {stored_count}/{len(normalized_events)} events stored"
            )
            
        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(str(e))
            logger.error(f"Job {job.name} failed: {e}")
        
        result["end_time"] = datetime.utcnow().isoformat()
        
        # Log ingestion run
        self._log_ingestion_run(result)
        
        return result
    
    def run_all_jobs(self) -> List[Dict[str, Any]]:
        """Run all configured jobs and return results."""
        run_id = str(uuid.uuid4())
        results = []
        
        logger.info(f"Starting ingestion run {run_id} with {len(self.jobs)} jobs")
        
        for job in self.jobs:
            result = self.run_job(job, run_id=run_id)
            results.append(result)
        
        # Summary
        total_fetched = sum(r["events_fetched"] for r in results)
        total_stored = sum(r["events_stored"] for r in results)
        
        logger.info(
            f"Completed ingestion run {run_id}: "
            f"{total_fetched} fetched, {total_stored} stored"
        )
        
        return results
    
    def _store_event(self, event: NormalizedEvent):
        """
        Store a normalized event in the database.
        
        Args:
            event: Normalized event to store
        """
        # Check if event already exists
        existing = self.db.get_event_by_id(event.event_id)
        
        if existing:
            # Update existing event
            self.db.update(
                "events",
                {
                    "start_time": event.start_time,
                    "updated_at": datetime.utcnow().isoformat(),
                    "metadata": json.dumps(event.metadata) if event.metadata else None,
                },
                "event_id = ?",
                (event.event_id,),
            )
        else:
            # Insert new event
            event_data = event.to_database_event()
            self.db.insert("events", event_data, return_id=False)
        
        # Insert odds record
        odds_data = event.to_database_odds()
        self.db.insert("odds", odds_data, return_id=False)
    
    def _log_ingestion_run(self, result: Dict[str, Any]):
        """Log ingestion run to database."""
        try:
            log_data = {
                "run_id": result["run_id"],
                "source": result["job_name"],
                "start_time": result["start_time"],
                "end_time": result.get("end_time"),
                "status": result["status"],
                "events_fetched": result["events_fetched"],
                "events_normalized": result["events_normalized"],
                "events_stored": result["events_stored"],
                "errors": json.dumps(result["errors"]) if result["errors"] else None,
            }
            self.db.insert("ingestion_log", log_data, return_id=False)
        except Exception as e:
            logger.error(f"Failed to log ingestion run: {e}")
    
    def start_scheduler(
        self,
        interval_seconds: int = 3600,
        run_immediately: bool = True
    ):
        """
        Start the scheduler in a background thread.
        
        Args:
            interval_seconds: Seconds between runs
            run_immediately: Whether to run immediately or wait for first interval
        """
        if self._running:
            logger.warning("Scheduler is already running")
            return
        
        self._interval_seconds = interval_seconds
        self._stop_event.clear()
        self._running = True
        
        def scheduler_loop():
            if run_immediately:
                self.run_all_jobs()
            
            while not self._stop_event.is_set():
                # Wait for interval or until stopped
                if self._stop_event.wait(interval_seconds):
                    break
                
                if not self._stop_event.is_set():
                    self.run_all_jobs()
        
        self._scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info(f"Scheduler started with {interval_seconds}s interval")
    
    def stop_scheduler(self):
        """Stop the background scheduler."""
        if not self._running:
            return
        
        self._stop_event.set()
        self._running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        
        logger.info("Scheduler stopped")
    
    def get_ingestion_stats(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get ingestion statistics.
        
        Args:
            hours: Lookback period in hours
            
        Returns:
            Dict with statistics
        """
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        # Get log entries
        logs = self.db.execute(
            """
            SELECT * FROM ingestion_log 
            WHERE start_time > ?
            ORDER BY start_time DESC
            """,
            (since,),
        )
        
        # Calculate stats
        total_runs = len(logs)
        successful_runs = sum(1 for l in logs if l["status"] == "success")
        failed_runs = sum(1 for l in logs if l["status"] == "failed")
        total_fetched = sum(l["events_fetched"] for l in logs)
        total_stored = sum(l["events_stored"] for l in logs)
        
        return {
            "period_hours": hours,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "total_events_fetched": total_fetched,
            "total_events_stored": total_stored,
            "recent_runs": logs[:10],
        }


def run_ingestion_job(
    sportsbook_client: Optional[str] = None,
    prediction_market_client: Optional[str] = None,
    sport: str = "NBA",
    category: str = "sports",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run a single ingestion job.
    
    Args:
        sportsbook_client: Sportsbook client type ('odds_api' or 'mock')
        prediction_market_client: PM client type ('polymarket', 'kalshi', or 'mock')
        sport: Sport to fetch from sportsbook
        category: Category to fetch from prediction markets
        db_path: Database path
        
    Returns:
        Job results
    """
    scheduler = IngestionScheduler(db_path=db_path)
    
    if sportsbook_client:
        scheduler.add_sportsbook_job(
            name=f"sportsbook_{sportsbook_client}",
            client_type=sportsbook_client,
            sport=sport,
        )
    
    if prediction_market_client:
        scheduler.add_prediction_market_job(
            name=f"prediction_market_{prediction_market_client}",
            client_type=prediction_market_client,
            category=category,
        )
    
    results = scheduler.run_all_jobs()
    
    return {
        "run_completed": True,
        "jobs_run": len(results),
        "results": results,
    }


# CLI entry point
def main():
    """CLI entry point for running ingestion."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data ingestion for Arbitrage Hunter")
    parser.add_argument(
        "--sportsbook",
        choices=["odds_api", "mock"],
        help="Sportsbook client type",
    )
    parser.add_argument(
        "--prediction-market",
        choices=["polymarket", "kalshi", "mock"],
        help="Prediction market client type",
    )
    parser.add_argument("--sport", default="NBA", help="Sport to fetch")
    parser.add_argument("--category", default="sports", help="PM category")
    parser.add_argument("--db-path", help="Database path")
    parser.add_argument(
        "--schedule",
        type=int,
        metavar="SECONDS",
        help="Run on schedule (interval in seconds)",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    scheduler = IngestionScheduler(db_path=args.db_path)
    
    if args.sportsbook:
        scheduler.add_sportsbook_job(
            name=f"sportsbook_{args.sportsbook}",
            client_type=args.sportsbook,
            sport=args.sport,
        )
    
    if args.prediction_market:
        scheduler.add_prediction_market_job(
            name=f"prediction_market_{args.prediction_market}",
            client_type=args.prediction_market,
            category=args.category,
        )
    
    if args.schedule:
        # Run on schedule
        scheduler.start_scheduler(interval_seconds=args.schedule)
        
        try:
            # Keep running until interrupted
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.stop_scheduler()
    else:
        # Run once
        results = scheduler.run_all_jobs()
        
        # Print summary
        print("\n=== Ingestion Results ===")
        for result in results:
            print(f"\nJob: {result['job_name']}")
            print(f"  Status: {result['status']}")
            print(f"  Fetched: {result['events_fetched']}")
            print(f"  Normalized: {result['events_normalized']}")
            print(f"  Stored: {result['events_stored']}")
            if result["errors"]:
                print(f"  Errors: {len(result['errors'])}")


if __name__ == "__main__":
    main()
