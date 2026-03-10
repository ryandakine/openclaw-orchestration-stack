"""
Runtime Configuration.

Mutable configuration that can be changed at runtime without restart.
Used for operational controls like log level and dry-run mode.
"""

from dataclasses import dataclass, field
from typing import Literal, Callable, Self
from threading import Lock
import logging


@dataclass
class RuntimeConfig:
    """
    Mutable runtime configuration.
    
    Unlike other config classes that are frozen at startup,
    this class allows runtime modifications for operational controls.
    
    Thread-safe using internal locking.
    
    Attributes:
        log_level: Current logging level (can be changed at runtime)
        dry_run: Force dry-run mode regardless of config
        pause_scanning: Pause the arbitrage scanner
        max_concurrent_scans: Runtime-adjustable scan limit
        circuit_breaker_threshold: Error threshold to pause trading
    """
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = field(default="INFO")
    """Current logging level - can be changed at runtime."""
    
    # Safety controls
    force_dry_run: bool = field(default=True)
    """
    Force dry-run mode regardless of config file settings.
    This is a safety switch that overrides everything.
    """
    
    pause_scanning: bool = field(default=False)
    """Pause the arbitrage scanner (emergency stop)."""
    
    pause_executions: bool = field(default=False)
    """Pause trade executions but keep scanning."""
    
    # Operational limits
    max_concurrent_scans: int = field(default=10)
    """Runtime-adjustable maximum concurrent scans."""
    
    max_daily_trades: int | None = field(default=None)
    """Maximum trades per day (None = unlimited)."""
    
    max_daily_exposure_usd: float | None = field(default=None)
    """Maximum daily exposure in USD (None = unlimited)."""
    
    # Circuit breaker
    circuit_breaker_enabled: bool = field(default=True)
    """Enable automatic circuit breaker on errors."""
    
    circuit_breaker_threshold: int = field(default=5)
    """Number of consecutive errors before circuit breaker trips."""
    
    circuit_breaker_reset_seconds: float = field(default=300.0)
    """Seconds to wait before resetting circuit breaker."""
    
    # Performance tuning
    scan_interval_multiplier: float = field(default=1.0)
    """Multiplier for scan intervals (>1 = slower, <1 = faster)."""
    
    cache_ttl_multiplier: float = field(default=1.0)
    """Multiplier for cache TTL (>1 = longer cache, <1 = shorter)."""
    
    # Feature toggles (runtime)
    enable_detailed_logging: bool = field(default=False)
    """Enable verbose per-opportunity logging."""
    
    enable_request_trace: bool = field(default=False)
    """Enable HTTP request/response tracing."""
    
    # Alerting
    alert_cooldown_seconds: float = field(default=60.0)
    """Minimum seconds between duplicate alerts."""
    
    # Internal state (not user-configurable)
    _lock: Lock = field(default_factory=Lock, repr=False)
    _change_callbacks: list = field(default_factory=list, repr=False)
    _circuit_breaker_tripped: bool = field(default=False, repr=False)
    _consecutive_errors: int = field(default=0, repr=False)
    
    def __post_init__(self):
        """Validate initial values."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate runtime configuration values."""
        if self.max_concurrent_scans < 1:
            raise ValueError("max_concurrent_scans must be at least 1")
        
        if self.scan_interval_multiplier <= 0:
            raise ValueError("scan_interval_multiplier must be positive")
        
        if self.cache_ttl_multiplier <= 0:
            raise ValueError("cache_ttl_multiplier must be positive")
        
        if self.circuit_breaker_threshold < 1:
            raise ValueError("circuit_breaker_threshold must be at least 1")
        
        if self.alert_cooldown_seconds < 0:
            raise ValueError("alert_cooldown_seconds must be non-negative")
    
    def set_log_level(self, level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]) -> None:
        """Change logging level at runtime."""
        with self._lock:
            old_level = self.log_level
            self.log_level = level
            logging.getLogger().setLevel(getattr(logging, level))
        self._notify_change("log_level", level, old_level)
    
    def set_dry_run(self, enabled: bool) -> None:
        """Enable/disable forced dry-run mode."""
        with self._lock:
            old_value = self.force_dry_run
            self.force_dry_run = enabled
        self._notify_change("force_dry_run", enabled, old_value)
    
    def set_pause_scanning(self, paused: bool) -> None:
        """Pause or resume scanning."""
        with self._lock:
            old_value = self.pause_scanning
            self.pause_scanning = paused
        self._notify_change("pause_scanning", paused, old_value)
    
    def set_pause_executions(self, paused: bool) -> None:
        """Pause or resume trade executions."""
        with self._lock:
            old_value = self.pause_executions
            self.pause_executions = paused
        self._notify_change("pause_executions", paused, old_value)
    
    def set_max_concurrent_scans(self, limit: int) -> None:
        """Adjust max concurrent scans at runtime."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._lock:
            old_value = self.max_concurrent_scans
            self.max_concurrent_scans = limit
        self._notify_change("max_concurrent_scans", limit, old_value)
    
    def set_scan_speed(self, multiplier: float) -> None:
        """Adjust scan speed multiplier."""
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        with self._lock:
            old_value = self.scan_interval_multiplier
            self.scan_interval_multiplier = multiplier
        self._notify_change("scan_interval_multiplier", multiplier, old_value)
    
    def record_error(self) -> bool:
        """Record an error for circuit breaker logic. Returns True if tripped."""
        with self._lock:
            self._consecutive_errors += 1
            if self.circuit_breaker_enabled and not self._circuit_breaker_tripped:
                if self._consecutive_errors >= self.circuit_breaker_threshold:
                    self._circuit_breaker_tripped = True
                    self.pause_executions = True
                    return True
            return False
    
    def record_success(self) -> None:
        """Record a success (resets consecutive error counter)."""
        with self._lock:
            self._consecutive_errors = 0
    
    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            old_tripped = self._circuit_breaker_tripped
            self._circuit_breaker_tripped = False
            self._consecutive_errors = 0
            self.pause_executions = False
        if old_tripped:
            self._notify_change("circuit_breaker", "reset", "tripped")
    
    def is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is currently tripped."""
        with self._lock:
            return self._circuit_breaker_tripped
    
    def can_scan(self) -> bool:
        """Check if scanning is allowed."""
        with self._lock:
            return not self.pause_scanning
    
    def can_execute(self) -> bool:
        """Check if trade execution is allowed."""
        with self._lock:
            if self.pause_executions:
                return False
            if self._circuit_breaker_tripped:
                return False
            if self.force_dry_run:
                return False
            return True
    
    def is_dry_run(self) -> bool:
        """Check if currently in dry-run mode."""
        with self._lock:
            return self.force_dry_run
    
    def get_status(self) -> dict:
        """Get current runtime status as dictionary."""
        with self._lock:
            return {
                "log_level": self.log_level,
                "force_dry_run": self.force_dry_run,
                "pause_scanning": self.pause_scanning,
                "pause_executions": self.pause_executions,
                "can_scan": not self.pause_scanning,
                "can_execute": not (self.pause_executions or self._circuit_breaker_tripped or self.force_dry_run),
                "circuit_breaker_tripped": self._circuit_breaker_tripped,
                "consecutive_errors": self._consecutive_errors,
                "max_concurrent_scans": self.max_concurrent_scans,
                "scan_interval_multiplier": self.scan_interval_multiplier,
            }
    
    def register_change_callback(self, callback: Callable) -> None:
        """Register a callback for configuration changes."""
        with self._lock:
            if callback not in self._change_callbacks:
                self._change_callbacks.append(callback)
    
    def unregister_change_callback(self, callback: Callable) -> None:
        """Unregister a change callback."""
        with self._lock:
            if callback in self._change_callbacks:
                self._change_callbacks.remove(callback)
    
    def _notify_change(self, key: str, new_value: any, old_value: any) -> None:
        """Notify all registered callbacks of a change."""
        callbacks = []
        with self._lock:
            callbacks = self._change_callbacks.copy()
        for callback in callbacks:
            try:
                callback(key, new_value, old_value)
            except Exception:
                pass  # Don't let callbacks break the config
    
    def to_dict(self) -> dict:
        """Convert to dictionary (excludes internal state)."""
        return {
            "log_level": self.log_level,
            "force_dry_run": self.force_dry_run,
            "pause_scanning": self.pause_scanning,
            "pause_executions": self.pause_executions,
            "max_concurrent_scans": self.max_concurrent_scans,
            "max_daily_trades": self.max_daily_trades,
            "max_daily_exposure_usd": self.max_daily_exposure_usd,
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_breaker_reset_seconds": self.circuit_breaker_reset_seconds,
            "scan_interval_multiplier": self.scan_interval_multiplier,
            "cache_ttl_multiplier": self.cache_ttl_multiplier,
            "enable_detailed_logging": self.enable_detailed_logging,
            "enable_request_trace": self.enable_request_trace,
            "alert_cooldown_seconds": self.alert_cooldown_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    @classmethod
    def from_env(cls) -> Self:
        """Create from environment variables."""
        import os
        
        def env_bool(name: str, default: bool = False) -> bool:
            return os.getenv(name, str(default).lower()).lower() in ("true", "1", "yes", "on")
        
        def env_float(name: str, default: float) -> float:
            return float(os.getenv(name, str(default)))
        
        def env_int(name: str, default: int) -> int:
            return int(os.getenv(name, str(default)))
        
        return cls(
            log_level=os.getenv("RUNTIME_LOG_LEVEL", "INFO"),  # type: ignore
            force_dry_run=env_bool("RUNTIME_FORCE_DRY_RUN", True),
            pause_scanning=env_bool("RUNTIME_PAUSE_SCANNING", False),
            pause_executions=env_bool("RUNTIME_PAUSE_EXECUTIONS", False),
            max_concurrent_scans=env_int("RUNTIME_MAX_CONCURRENT_SCANS", 10),
            max_daily_trades=env_int("RUNTIME_MAX_DAILY_TRADES", 0) or None,
            max_daily_exposure_usd=env_float("RUNTIME_MAX_DAILY_EXPOSURE_USD", 0) or None,
            circuit_breaker_enabled=env_bool("RUNTIME_CIRCUIT_BREAKER_ENABLED", True),
            circuit_breaker_threshold=env_int("RUNTIME_CIRCUIT_BREAKER_THRESHOLD", 5),
            circuit_breaker_reset_seconds=env_float("RUNTIME_CIRCUIT_BREAKER_RESET_SECONDS", 300.0),
            scan_interval_multiplier=env_float("RUNTIME_SCAN_INTERVAL_MULTIPLIER", 1.0),
            cache_ttl_multiplier=env_float("RUNTIME_CACHE_TTL_MULTIPLIER", 1.0),
            enable_detailed_logging=env_bool("RUNTIME_ENABLE_DETAILED_LOGGING", False),
            enable_request_trace=env_bool("RUNTIME_ENABLE_REQUEST_TRACE", False),
            alert_cooldown_seconds=env_float("RUNTIME_ALERT_COOLDOWN_SECONDS", 60.0),
        )


# Singleton instance
_runtime_config: RuntimeConfig | None = None


def get_runtime_config() -> RuntimeConfig:
    """Get the singleton runtime config instance."""
    global _runtime_config
    if _runtime_config is None:
        _runtime_config = RuntimeConfig()
    return _runtime_config


def set_runtime_config(config: RuntimeConfig) -> None:
    """Set the singleton runtime config instance."""
    global _runtime_config
    _runtime_config = config
