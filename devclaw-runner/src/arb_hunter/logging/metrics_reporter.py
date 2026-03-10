"""
metrics_reporter.py - Prometheus-style metrics for operational monitoring.

Provides counters, gauges, and histograms for key arbitrage hunting metrics
compatible with Prometheus scraping format.
"""

import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from collections import defaultdict

import structlog

from .logger_config import get_logger


class MetricType(str, Enum):
    """Types of metrics supported."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """A single metric value with labels."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[float] = None
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus exposition format."""
        label_str = ""
        if self.labels:
            label_parts = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(label_parts) + "}"
        
        timestamp = f" {int(self.timestamp)}" if self.timestamp else ""
        return f"{self.name}{label_str} {self.value}{timestamp}"


@dataclass
class MetricDefinition:
    """Definition of a metric."""
    name: str
    metric_type: MetricType
    description: str
    unit: Optional[str] = None
    label_names: List[str] = field(default_factory=list)


class MetricsReporter:
    """
    Prometheus-style metrics reporter.
    
    Tracks operational metrics for arbitrage hunting including
    counters, gauges, and histograms with label support.
    """
    
    # Standard metric definitions
    METRIC_MARKETS_SCANNED = MetricDefinition(
        name="arb_hunter_markets_scanned_total",
        metric_type=MetricType.COUNTER,
        description="Total number of markets scanned",
        label_names=["source", "sport", "status"]
    )
    
    METRIC_ARBS_FOUND = MetricDefinition(
        name="arb_hunter_arbitrage_opportunities_total",
        metric_type=MetricType.COUNTER,
        description="Total arbitrage opportunities found",
        label_names=["source_pair", "priority"]
    )
    
    METRIC_ALERTS_SENT = MetricDefinition(
        name="arb_hunter_alerts_sent_total",
        metric_type=MetricType.COUNTER,
        description="Total alerts sent",
        label_names=["channel", "priority", "status"]
    )
    
    METRIC_MATCHES_FOUND = MetricDefinition(
        name="arb_hunter_matches_total",
        metric_type=MetricType.COUNTER,
        description="Total market matches found",
        label_names=["source_pair", "confidence"]
    )
    
    METRIC_SCAN_DURATION = MetricDefinition(
        name="arb_hunter_scan_duration_seconds",
        metric_type=MetricType.HISTOGRAM,
        description="Time taken for scan runs",
        unit="seconds",
        label_names=["status"]
    )
    
    METRIC_API_LATENCY = MetricDefinition(
        name="arb_hunter_api_request_duration_seconds",
        metric_type=MetricType.HISTOGRAM,
        description="API request latency",
        unit="seconds",
        label_names=["source", "endpoint"]
    )
    
    METRIC_ACTIVE_RUNS = MetricDefinition(
        name="arb_hunter_active_runs",
        metric_type=MetricType.GAUGE,
        description="Number of currently active scan runs"
    )
    
    METRIC_ERRORS = MetricDefinition(
        name="arb_hunter_errors_total",
        metric_type=MetricType.COUNTER,
        description="Total errors encountered",
        label_names=["error_type", "source"]
    )
    
    METRIC_EDGE_PERCENT = MetricDefinition(
        name="arb_hunter_edge_percent",
        metric_type=MetricType.GAUGE,
        description="Edge percentage of identified opportunities",
        label_names=["source_pair"]
    )
    
    def __init__(self, metrics_dir: Optional[Path] = None):
        self.logger = get_logger("metrics_reporter")
        self.metrics_dir = Path(metrics_dir) if metrics_dir else None
        
        # Storage for metric values
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        
        # Metric definitions
        self._definitions: Dict[str, MetricDefinition] = {}
        
        # Register standard metrics
        self._register_standard_metrics()
    
    def _register_standard_metrics(self) -> None:
        """Register standard metric definitions."""
        for attr_name in dir(self):
            if attr_name.startswith("METRIC_"):
                metric_def = getattr(self, attr_name)
                if isinstance(metric_def, MetricDefinition):
                    self._definitions[metric_def.name] = metric_def
    
    def register_metric(self, definition: MetricDefinition) -> None:
        """Register a custom metric definition."""
        self._definitions[definition.name] = definition
    
    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Increment a counter metric.
        
        Args:
            name: Metric name
            value: Amount to increment by
            labels: Label values
        """
        label_key = self._labels_to_key(labels or {})
        self._counters[name][label_key] += value
        
        self.logger.debug(
            "metric_counter_incremented",
            metric_name=name,
            value=value,
            labels=labels
        )
    
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Set a gauge metric value.
        
        Args:
            name: Metric name
            value: Gauge value
            labels: Label values
        """
        label_key = self._labels_to_key(labels or {})
        self._gauges[name][label_key] = value
    
    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Observe a value for a histogram metric.
        
        Args:
            name: Metric name
            value: Value to observe
            labels: Label values
        """
        label_key = self._labels_to_key(labels or {})
        self._histograms[name][label_key].append(value)
    
    def record_markets_scanned(
        self,
        count: int,
        source: str,
        sport: str = "unknown",
        status: str = "success"
    ) -> None:
        """Record markets scanned metric."""
        self.increment_counter(
            self.METRIC_MARKETS_SCANNED.name,
            value=float(count),
            labels={"source": source, "sport": sport, "status": status}
        )
    
    def record_arbitrage_found(
        self,
        source_pair: str,
        priority: str,
        edge_percent: float
    ) -> None:
        """Record arbitrage opportunity found."""
        self.increment_counter(
            self.METRIC_ARBS_FOUND.name,
            labels={"source_pair": source_pair, "priority": priority}
        )
        
        # Also update edge gauge
        self.set_gauge(
            self.METRIC_EDGE_PERCENT.name,
            value=edge_percent,
            labels={"source_pair": source_pair}
        )
    
    def record_alert_sent(
        self,
        channel: str,
        priority: str,
        status: str = "success"
    ) -> None:
        """Record alert sent metric."""
        self.increment_counter(
            self.METRIC_ALERTS_SENT.name,
            labels={"channel": channel, "priority": priority, "status": status}
        )
    
    def record_match(
        self,
        source_pair: str,
        confidence: str
    ) -> None:
        """Record match found metric."""
        self.increment_counter(
            self.METRIC_MATCHES_FOUND.name,
            labels={"source_pair": source_pair, "confidence": confidence}
        )
    
    def record_scan_duration(
        self,
        duration_seconds: float,
        status: str = "success"
    ) -> None:
        """Record scan duration metric."""
        self.observe_histogram(
            self.METRIC_SCAN_DURATION.name,
            value=duration_seconds,
            labels={"status": status}
        )
    
    def record_api_latency(
        self,
        source: str,
        endpoint: str,
        latency_seconds: float
    ) -> None:
        """Record API latency metric."""
        self.observe_histogram(
            self.METRIC_API_LATENCY.name,
            value=latency_seconds,
            labels={"source": source, "endpoint": endpoint}
        )
    
    def record_error(
        self,
        error_type: str,
        source: str = "unknown"
    ) -> None:
        """Record error metric."""
        self.increment_counter(
            self.METRIC_ERRORS.name,
            labels={"error_type": error_type, "source": source}
        )
    
    def set_active_runs(self, count: int) -> None:
        """Update active runs gauge."""
        self.set_gauge(self.METRIC_ACTIVE_RUNS.name, value=float(count))
    
    def get_prometheus_format(self) -> str:
        """
        Export all metrics in Prometheus exposition format.
        
        Returns:
            Metrics in Prometheus text format
        """
        lines = []
        timestamp = time.time()
        
        # Process counters
        for name, label_values in self._counters.items():
            if name in self._definitions:
                defn = self._definitions[name]
                lines.append(f"# HELP {name} {defn.description}")
                lines.append(f"# TYPE {name} {defn.metric_type.value}")
            
            for label_key, value in label_values.items():
                labels = self._key_to_labels(label_key)
                label_str = self._format_labels(labels)
                lines.append(f"{name}{label_str} {value}")
        
        # Process gauges
        for name, label_values in self._gauges.items():
            if name in self._definitions:
                defn = self._definitions[name]
                lines.append(f"# HELP {name} {defn.description}")
                lines.append(f"# TYPE {name} {defn.metric_type.value}")
            
            for label_key, value in label_values.items():
                labels = self._key_to_labels(label_key)
                label_str = self._format_labels(labels)
                lines.append(f"{name}{label_str} {value}")
        
        # Process histograms
        for name, label_values in self._histograms.items():
            if name in self._definitions:
                defn = self._definitions[name]
                lines.append(f"# HELP {name} {defn.description}")
                lines.append(f"# TYPE {name} {defn.metric_type.value}")
            
            for label_key, values in label_values.items():
                labels = self._key_to_labels(label_key)
                
                # Calculate buckets (simplified)
                buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
                
                for bucket in buckets:
                    count = len([v for v in values if v <= bucket])
                    bucket_labels = {**labels, "le": str(bucket)}
                    label_str = self._format_labels(bucket_labels)
                    lines.append(f"{name}_bucket{label_str} {count}")
                
                # +Inf bucket
                inf_labels = {**labels, "le": "+Inf"}
                label_str = self._format_labels(inf_labels)
                lines.append(f"{name}_bucket{label_str} {len(values)}")
                
                # Sum and count
                label_str = self._format_labels(labels)
                lines.append(f"{name}_sum{label_str} {sum(values)}")
                lines.append(f"{name}_count{label_str} {len(values)}")
        
        return "\n".join(lines)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        summary = {
            "counters": {},
            "gauges": {},
            "histograms": {}
        }
        
        # Summarize counters
        for name, label_values in self._counters.items():
            total = sum(label_values.values())
            summary["counters"][name] = {
                "total": total,
                "by_labels": dict(label_values)
            }
        
        # Summarize gauges
        for name, label_values in self._gauges.items():
            summary["gauges"][name] = dict(label_values)
        
        # Summarize histograms
        for name, label_values in self._histograms.items():
            hist_summary = {}
            for label_key, values in label_values.items():
                if values:
                    hist_summary[label_key] = {
                        "count": len(values),
                        "sum": sum(values),
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "p50": sorted(values)[len(values) // 2] if values else 0,
                        "p95": sorted(values)[int(len(values) * 0.95)] if values else 0,
                        "p99": sorted(values)[int(len(values) * 0.99)] if values else 0
                    }
            summary["histograms"][name] = hist_summary
        
        return summary
    
    def write_prometheus_file(self, file_path: Optional[Path] = None) -> Path:
        """
        Write metrics to a Prometheus exposition format file.
        
        Args:
            file_path: Output file path (default: metrics_dir/prometheus.metrics)
            
        Returns:
            Path to the written file
        """
        if file_path is None:
            if self.metrics_dir is None:
                raise ValueError("Either file_path or metrics_dir must be set")
            file_path = self.metrics_dir / "prometheus.metrics"
        
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = self.get_prometheus_format()
        with open(file_path, "w") as f:
            f.write(content)
            f.write("\n")
        
        return file_path
    
    def reset_metrics(self) -> None:
        """Reset all metrics to zero (counters are preserved, gauges/histograms cleared)."""
        self._gauges.clear()
        self._histograms.clear()
        self.logger.info("metrics_reset")
    
    def _labels_to_key(self, labels: Dict[str, str]) -> str:
        """Convert labels dict to a sortable key string."""
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def _key_to_labels(self, key: str) -> Dict[str, str]:
        """Convert key string back to labels dict."""
        if not key:
            return {}
        labels = {}
        for part in key.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k] = v
        return labels
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus output."""
        if not labels:
            return ""
        label_parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(label_parts) + "}"


# Singleton instance
_metrics_reporter_instance: Optional[MetricsReporter] = None


def initialize_metrics_reporter(metrics_dir: Optional[Path] = None) -> MetricsReporter:
    """Initialize the global metrics reporter instance."""
    global _metrics_reporter_instance
    _metrics_reporter_instance = MetricsReporter(metrics_dir=metrics_dir)
    return _metrics_reporter_instance


def get_metrics_reporter() -> MetricsReporter:
    """Get the global metrics reporter instance."""
    if _metrics_reporter_instance is None:
        return MetricsReporter()
    return _metrics_reporter_instance
