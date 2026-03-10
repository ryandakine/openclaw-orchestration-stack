"""
OpenClaw Arbitrage Hunter - Main Orchestrator Module

Coordinates all modules to scan for arbitrage opportunities between
Polymarket prediction markets and traditional sportsbooks.
"""

from .config_loader import Config, ConfigLoader
from .job_context import JobContext
from .fetch_all_sources import fetch_all_sources
from .normalize_all import normalize_all
from .match_all import match_all
from .calculate_all_arbs import calculate_all_arbs
from .filter_and_rank import filter_and_rank
from .send_alerts import send_alerts
from .audit_logger import AuditLogger
from .main_runner import main, run_arb_hunt

__version__ = "1.0.0"
__all__ = [
    "Config",
    "ConfigLoader",
    "JobContext",
    "fetch_all_sources",
    "normalize_all",
    "match_all",
    "calculate_all_arbs",
    "filter_and_rank",
    "send_alerts",
    "AuditLogger",
    "main",
    "run_arb_hunt",
]
