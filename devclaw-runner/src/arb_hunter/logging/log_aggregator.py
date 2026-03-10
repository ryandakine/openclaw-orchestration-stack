"""
log_aggregator.py - Aggregate logs for analysis: daily summary, trend detection.

Provides log aggregation capabilities including daily summaries, trend detection,
and statistical analysis of arbitrage hunting operations over time.
"""

import json
import statistics
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from collections import defaultdict

import structlog

from .logger_config import get_logger


@dataclass
class DailySummary:
    """Summary of a day's arbitrage hunting activity."""
    date: str  # ISO date string
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_markets_scanned: int = 0
    total_matches_found: int = 0
    total_arbs_found: int = 0
    total_alerts_sent: int = 0
    total_errors: int = 0
    avg_scan_duration_seconds: Optional[float] = None
    max_edge_percent: float = 0.0
    avg_edge_percent: Optional[float] = None
    # Source breakdown
    markets_by_source: Dict[str, int] = field(default_factory=dict)
    errors_by_category: Dict[str, int] = field(default_factory=dict)


@dataclass
class TrendPoint:
    """A single point in a trend series."""
    timestamp: str
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrendAnalysis:
    """Analysis of a trend over time."""
    metric_name: str
    time_range_days: int
    data_points: List[TrendPoint] = field(default_factory=list)
    trend_direction: str = "stable"  # increasing, decreasing, stable, volatile
    change_percent: float = 0.0
    avg_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    std_deviation: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "time_range_days": self.time_range_days,
            "trend_direction": self.trend_direction,
            "change_percent": self.change_percent,
            "avg_value": self.avg_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "std_deviation": self.std_deviation,
            "data_points": [
                {"timestamp": p.timestamp, "value": p.value, **p.metadata}
                for p in self.data_points
            ]
        }


class LogAggregator:
    """
    Log aggregation and analysis system.
    
    Aggregates logs across runs and time periods to provide:
    - Daily summaries
    - Trend detection
    - Statistical analysis
    - Comparative reporting
    """
    
    def __init__(self, log_dir: Path, aggregation_dir: Optional[Path] = None):
        self.logger = get_logger("log_aggregator")
        self.log_dir = Path(log_dir)
        self.aggregation_dir = Path(aggregation_dir) if aggregation_dir else self.log_dir / "aggregations"
        self.aggregation_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded data
        self._daily_cache: Dict[str, DailySummary] = {}
    
    def generate_daily_summary(self, date: Optional[datetime] = None) -> DailySummary:
        """
        Generate a summary for a specific day.
        
        Args:
            date: Date to summarize (defaults to today)
            
        Returns:
            DailySummary for the date
        """
        if date is None:
            date = datetime.now(timezone.utc)
        
        date_str = date.strftime("%Y-%m-%d")
        
        # Check cache
        if date_str in self._daily_cache:
            return self._daily_cache[date_str]
        
        summary = DailySummary(date=date_str)
        
        # Load run records for the date
        runs_dir = self.log_dir / "runs" / date_str
        if runs_dir.exists():
            for run_file in runs_dir.glob("*.json"):
                try:
                    with open(run_file, "r") as f:
                        run_data = json.load(f)
                    
                    summary.total_runs += 1
                    
                    if run_data.get("success"):
                        summary.successful_runs += 1
                    else:
                        summary.failed_runs += 1
                    
                    # Extract metrics
                    metrics = run_data.get("metrics", {})
                    summary.total_markets_scanned += metrics.get("markets_scanned", 0)
                    summary.total_matches_found += metrics.get("matches_found", 0)
                    summary.total_arbs_found += metrics.get("opportunities_identified", 0)
                    summary.total_alerts_sent += metrics.get("alerts_sent", 0)
                    
                    # Duration
                    duration = run_data.get("duration_seconds")
                    if duration:
                        if summary.avg_scan_duration_seconds is None:
                            summary.avg_scan_duration_seconds = duration
                        else:
                            # Running average
                            n = summary.total_runs
                            summary.avg_scan_duration_seconds = (
                                (summary.avg_scan_duration_seconds * (n - 1) + duration) / n
                            )
                    
                except Exception as e:
                    self.logger.warning(
                        "failed_to_process_run_file",
                        file=str(run_file),
                        error=str(e)
                    )
        
        # Load error records
        errors_dir = self.log_dir / "errors" / date_str
        if errors_dir.exists():
            for error_file in errors_dir.glob("*.json"):
                try:
                    with open(error_file, "r") as f:
                        error_data = json.load(f)
                    
                    summary.total_errors += len(error_data.get("errors", []))
                    
                    # Error categories
                    for error in error_data.get("errors", []):
                        category = error.get("category", "unknown")
                        summary.errors_by_category[category] = (
                            summary.errors_by_category.get(category, 0) + 1
                        )
                        
                except Exception as e:
                    self.logger.warning(
                        "failed_to_process_error_file",
                        file=str(error_file),
                        error=str(e)
                    )
        
        # Cache and return
        self._daily_cache[date_str] = summary
        return summary
    
    def generate_summary_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[DailySummary]:
        """
        Generate summaries for a date range.
        
        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            
        Returns:
            List of DailySummary objects
        """
        summaries = []
        current = start_date
        
        while current <= end_date:
            summary = self.generate_daily_summary(current)
            summaries.append(summary)
            current += timedelta(days=1)
        
        return summaries
    
    def analyze_trend(
        self,
        metric_name: str,
        days: int = 7,
        data_extractor: Optional[Callable[[DailySummary], float]] = None
    ) -> TrendAnalysis:
        """
        Analyze trends for a specific metric over time.
        
        Args:
            metric_name: Name of the metric to analyze
            days: Number of days to analyze
            data_extractor: Custom function to extract metric value from summary
            
        Returns:
            TrendAnalysis with direction and statistics
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        summaries = self.generate_summary_range(start_date, end_date)
        
        # Default extractors for common metrics
        if data_extractor is None:
            extractors = {
                "markets_scanned": lambda s: s.total_markets_scanned,
                "matches_found": lambda s: s.total_matches_found,
                "arbs_found": lambda s: s.total_arbs_found,
                "alerts_sent": lambda s: s.total_alerts_sent,
                "errors": lambda s: s.total_errors,
                "success_rate": lambda s: (
                    s.successful_runs / s.total_runs * 100 if s.total_runs > 0 else 0
                ),
                "scan_duration": lambda s: s.avg_scan_duration_seconds or 0
            }
            data_extractor = extractors.get(metric_name, lambda s: 0)
        
        # Build trend points
        data_points = []
        values = []
        
        for summary in summaries:
            value = data_extractor(summary)
            values.append(value)
            data_points.append(TrendPoint(
                timestamp=summary.date,
                value=value,
                metadata={
                    "total_runs": summary.total_runs,
                    "successful_runs": summary.successful_runs
                }
            ))
        
        # Calculate statistics
        analysis = TrendAnalysis(
            metric_name=metric_name,
            time_range_days=days,
            data_points=data_points
        )
        
        if values:
            analysis.avg_value = statistics.mean(values)
            analysis.min_value = min(values)
            analysis.max_value = max(values)
            
            if len(values) > 1:
                analysis.std_deviation = statistics.stdev(values)
                
                # Calculate trend direction
                first_half = values[:len(values)//2]
                second_half = values[len(values)//2:]
                
                if first_half and second_half:
                    first_avg = statistics.mean(first_half)
                    second_avg = statistics.mean(second_half)
                    
                    if first_avg > 0:
                        analysis.change_percent = (
                            (second_avg - first_avg) / first_avg * 100
                        )
                    
                    # Determine direction
                    if abs(analysis.change_percent) < 5:
                        analysis.trend_direction = "stable"
                    elif analysis.change_percent > 0:
                        analysis.trend_direction = "increasing"
                    else:
                        analysis.trend_direction = "decreasing"
                    
                    # Check for volatility
                    if analysis.std_deviation and analysis.avg_value:
                        cv = analysis.std_deviation / analysis.avg_value
                        if cv > 0.5:
                            analysis.trend_direction = "volatile"
        
        return analysis
    
    def detect_anomalies(
        self,
        metric_name: str,
        days: int = 7,
        threshold_std: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalous values in a metric time series.
        
        Args:
            metric_name: Metric to analyze
            days: Number of days to analyze
            threshold_std: Standard deviations for anomaly threshold
            
        Returns:
            List of anomaly detections
        """
        trend = self.analyze_trend(metric_name, days)
        
        if not trend.data_points or trend.std_deviation is None:
            return []
        
        anomalies = []
        mean = trend.avg_value or 0
        std = trend.std_deviation
        
        for point in trend.data_points:
            z_score = (point.value - mean) / std if std > 0 else 0
            
            if abs(z_score) > threshold_std:
                anomalies.append({
                    "timestamp": point.timestamp,
                    "value": point.value,
                    "z_score": round(z_score, 2),
                    "deviation": "high" if z_score > 0 else "low",
                    "expected_range": [
                        round(mean - threshold_std * std, 2),
                        round(mean + threshold_std * std, 2)
                    ]
                })
        
        return anomalies
    
    def generate_weekly_report(self, week_start: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive weekly report.
        
        Args:
            week_start: Start of the week (defaults to last 7 days)
            
        Returns:
            Weekly report dictionary
        """
        if week_start is None:
            week_start = datetime.now(timezone.utc) - timedelta(days=7)
        
        week_end = week_start + timedelta(days=6)
        summaries = self.generate_summary_range(week_start, week_end)
        
        # Aggregate totals
        total_runs = sum(s.total_runs for s in summaries)
        total_markets = sum(s.total_markets_scanned for s in summaries)
        total_arbs = sum(s.total_arbs_found for s in summaries)
        total_alerts = sum(s.total_alerts_sent for s in summaries)
        total_errors = sum(s.total_errors for s in summaries)
        
        # Trends
        trends = {
            "markets_scanned": self.analyze_trend("markets_scanned", days=7).to_dict(),
            "arbs_found": self.analyze_trend("arbs_found", days=7).to_dict(),
            "errors": self.analyze_trend("errors", days=7).to_dict(),
            "success_rate": self.analyze_trend("success_rate", days=7).to_dict()
        }
        
        # Anomalies
        anomalies = {
            "arbs_found": self.detect_anomalies("arbs_found", days=7),
            "errors": self.detect_anomalies("errors", days=7)
        }
        
        report = {
            "report_type": "weekly",
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": week_end.strftime("%Y-%m-%d"),
            "summary": {
                "total_runs": total_runs,
                "total_markets_scanned": total_markets,
                "total_arbs_found": total_arbs,
                "total_alerts_sent": total_alerts,
                "total_errors": total_errors,
                "avg_arbs_per_run": round(total_arbs / total_runs, 2) if total_runs > 0 else 0,
                "alert_conversion_rate": round(total_alerts / total_arbs * 100, 2) if total_arbs > 0 else 0
            },
            "daily_breakdown": [asdict(s) for s in summaries],
            "trends": trends,
            "anomalies": anomalies,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
        return report
    
    def save_daily_summary(self, summary: DailySummary) -> Path:
        """Save a daily summary to disk."""
        file_path = self.aggregation_dir / f"summary_{summary.date}.json"
        
        with open(file_path, "w") as f:
            json.dump(asdict(summary), f, indent=2)
        
        return file_path
    
    def save_weekly_report(self, report: Dict[str, Any]) -> Path:
        """Save a weekly report to disk."""
        week_start = report.get("week_start", "unknown")
        file_path = self.aggregation_dir / f"weekly_report_{week_start}.json"
        
        with open(file_path, "w") as f:
            json.dump(report, f, indent=2)
        
        return file_path
    
    def compare_periods(
        self,
        period1_start: datetime,
        period1_end: datetime,
        period2_start: datetime,
        period2_end: datetime
    ) -> Dict[str, Any]:
        """
        Compare two time periods.
        
        Args:
            period1_start: Start of first period
            period1_end: End of first period
            period2_start: Start of second period
            period2_end: End of second period
            
        Returns:
            Comparison dictionary
        """
        summary1_list = self.generate_summary_range(period1_start, period1_end)
        summary2_list = self.generate_summary_range(period2_start, period2_end)
        
        # Aggregate each period
        def aggregate(summaries: List[DailySummary]) -> Dict[str, Any]:
            return {
                "total_runs": sum(s.total_runs for s in summaries),
                "total_markets": sum(s.total_markets_scanned for s in summaries),
                "total_arbs": sum(s.total_arbs_found for s in summaries),
                "total_alerts": sum(s.total_alerts_sent for s in summaries),
                "total_errors": sum(s.total_errors for s in summaries)
            }
        
        p1 = aggregate(summary1_list)
        p2 = aggregate(summary2_list)
        
        # Calculate changes
        changes = {}
        for key in p1.keys():
            if p1[key] > 0:
                changes[key] = round((p2[key] - p1[key]) / p1[key] * 100, 2)
            else:
                changes[key] = 0 if p2[key] == 0 else 100
        
        return {
            "period1": {
                "start": period1_start.isoformat(),
                "end": period1_end.isoformat(),
                **p1
            },
            "period2": {
                "start": period2_start.isoformat(),
                "end": period2_end.isoformat(),
                **p2
            },
            "changes_percent": changes
        }


# Singleton instance
_log_aggregator_instance: Optional[LogAggregator] = None


def initialize_log_aggregator(
    log_dir: Path,
    aggregation_dir: Optional[Path] = None
) -> LogAggregator:
    """Initialize the global log aggregator instance."""
    global _log_aggregator_instance
    _log_aggregator_instance = LogAggregator(
        log_dir=log_dir,
        aggregation_dir=aggregation_dir
    )
    return _log_aggregator_instance


def get_log_aggregator() -> LogAggregator:
    """Get the global log aggregator instance."""
    if _log_aggregator_instance is None:
        raise RuntimeError("Log aggregator not initialized. Call initialize_log_aggregator() first.")
    return _log_aggregator_instance
