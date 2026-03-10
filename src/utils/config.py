"""
Configuration loading module for the Sportsbook/Arbitrage Hunter.

Supports loading from YAML config files and environment variables.
Environment variables override config file values.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    enabled: bool = True
    url: str | None = None
    host: str = "localhost"
    port: int = 5432
    name: str = "openclaw"
    user: str = "openclaw"
    password: str | None = None
    pool_size: int = 10
    max_overflow: int = 20
    
    def get_url(self) -> str:
        """Get database URL, building from components if not set."""
        if self.url:
            return self.url
        password_part = f":{self.password}" if self.password else ""
        return f"postgresql://{self.user}{password_part}@{self.host}:{self.port}/{self.name}"


@dataclass
class SourceConfig:
    """Configuration for a single data source."""
    enabled: bool = False
    api_key: str | None = None
    api_secret: str | None = None
    api_url: str | None = None


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "structured"  # structured or simple
    log_file: str = "./logs/arbitrage_hunter.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    console_output: bool = True


@dataclass
class AuditConfig:
    """Audit logging configuration."""
    enabled: bool = True
    path: str = "./logs/audit"


@dataclass
class MetricsConfig:
    """Metrics and monitoring configuration."""
    enabled: bool = True
    port: int = 9090


@dataclass
class HealthCheckConfig:
    """Health check configuration."""
    enabled: bool = True
    interval_seconds: int = 30


@dataclass
class Config:
    """
    Main application configuration container.
    
    All settings are loaded from config.yaml and can be overridden
    by environment variables.
    """
    
    # Scheduling
    scan_interval_minutes: int = 5
    
    # Thresholds
    min_profit_threshold: float = 0.02
    min_edge_percent: float = 2.0
    min_profit_per_unit: float = 10.0
    max_stake_per_leg: float = 1000.0
    max_total_exposure: float = 5000.0
    
    # Sports configuration
    sports_to_scan: list[str] = field(default_factory=lambda: [
        "NBA", "NFL", "MLB", "NHL"
    ])
    
    # Alert configuration
    telegram_enabled: bool = True
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    top_n_alerts: int = 10
    alert_high_priority_threshold: float = 5.0
    alert_medium_priority_threshold: float = 3.0
    
    # Data sources
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    
    # Database
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    # Execution settings
    dry_run: bool = False
    enabled: bool = True
    max_concurrent_requests: int = 10
    request_delay_seconds: float = 0.1
    fetch_timeout_seconds: float = 30.0
    total_scan_timeout_seconds: float = 300.0
    
    # Logging
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Audit and monitoring
    audit_logging: AuditConfig = field(default_factory=AuditConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    
    def __post_init__(self):
        """Initialize default sources if not provided."""
        if not self.sources:
            self.sources = {
                "draftkings": SourceConfig(enabled=True),
                "fanduel": SourceConfig(enabled=True),
                "betmgm": SourceConfig(enabled=False),
                "caesars": SourceConfig(enabled=False),
                "polymarket": SourceConfig(enabled=True),
                "kalshi": SourceConfig(enabled=False),
            }
    
    def get_enabled_sources(self) -> dict[str, SourceConfig]:
        """Get all enabled data sources."""
        return {
            name: config for name, config in self.sources.items()
            if config.enabled
        }
    
    def get_enabled_sportsbooks(self) -> dict[str, SourceConfig]:
        """Get enabled sportsbook sources only."""
        sportsbooks = ["draftkings", "fanduel", "betmgm", "caesars"]
        return {
            name: config for name, config in self.sources.items()
            if name in sportsbooks and config.enabled
        }
    
    def get_enabled_prediction_markets(self) -> dict[str, SourceConfig]:
        """Get enabled prediction market sources only."""
        markets = ["polymarket", "kalshi"]
        return {
            name: config for name, config in self.sources.items()
            if name in markets and config.enabled
        }
    
    def is_source_configured(self, source_name: str) -> bool:
        """Check if a source has API credentials configured."""
        if source_name not in self.sources:
            return False
        source = self.sources[source_name]
        if not source.enabled:
            return False
        # Polymarket can work without API key (public API)
        if source_name == "polymarket":
            return True
        return source.api_key is not None


class ConfigLoader:
    """
    Loads configuration from YAML files and environment variables.
    
    Environment variables take precedence over config file values.
    Variable naming: ARB_HUNTER_SECTION_KEY (e.g., ARB_HUNTER_DATABASE_HOST)
    """
    
    ENV_PREFIX = "ARB_HUNTER_"
    DEFAULT_CONFIG_PATHS = [
        "./config.yaml",
        "./config.yml",
        "./config/config.yaml",
        "/etc/arbitrage-hunter/config.yaml",
    ]
    
    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """
        Load configuration from file and environment.
        
        Args:
            config_path: Path to config file (searches default paths if None)
        
        Returns:
            Config instance with all settings loaded
        
        Raises:
            FileNotFoundError: If no config file is found
        """
        # Find config file
        if config_path is None:
            config_path = cls._find_config_file()
        else:
            config_path = Path(config_path)
        
        # Load from file
        file_config = cls._load_from_file(config_path) if config_path.exists() else {}
        
        # Load from environment (overrides file values)
        env_config = cls._load_from_env()
        
        # Merge configs (env takes precedence)
        merged = cls._deep_merge(file_config, env_config)
        
        # Build Config object
        return cls._build_config(merged)
    
    @classmethod
    def _find_config_file(cls) -> Path:
        """Find config file in default locations."""
        for path in cls.DEFAULT_CONFIG_PATHS:
            if Path(path).exists():
                return Path(path)
        raise FileNotFoundError(
            f"No config file found. Searched: {', '.join(cls.DEFAULT_CONFIG_PATHS)}"
        )
    
    @classmethod
    def _load_from_file(cls, path: Path) -> dict[str, Any]:
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    
    @classmethod
    def _load_from_env(cls) -> dict[str, Any]:
        """Load configuration from environment variables."""
        config: dict[str, Any] = {}
        
        # Helper to set nested dict value
        def set_nested(d: dict, keys: list[str], value: Any):
            for key in keys[:-1]:
                d = d.setdefault(key, {})
            d[keys[-1]] = value
        
        for key, value in os.environ.items():
            if key.startswith(cls.ENV_PREFIX):
                # Convert ARB_HUNTER_DATABASE_HOST to database.host
                config_key = key[len(cls.ENV_PREFIX):].lower()
                keys = config_key.split("_")
                
                # Try to convert value to appropriate type
                typed_value = cls._convert_value(value)
                set_nested(config, keys, typed_value)
        
        return config
    
    @classmethod
    def _convert_value(cls, value: str) -> Any:
        """Convert string value to appropriate type."""
        # Try bool
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        
        # Try int
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string (handle 'null' specially)
        if value.lower() in ("null", "none", ""):
            return None
        
        return value
    
    @classmethod
    def _deep_merge(cls, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    @classmethod
    def _build_config(cls, data: dict[str, Any]) -> Config:
        """Build Config object from dictionary."""
        # Build sources
        sources_data = data.get("sources", {})
        sources = {}
        for name, source_data in sources_data.items():
            sources[name] = SourceConfig(
                enabled=source_data.get("enabled", False),
                api_key=source_data.get("api_key"),
                api_secret=source_data.get("api_secret"),
                api_url=source_data.get("api_url"),
            )
        
        # Build database config
        db_data = data.get("database", {})
        database = DatabaseConfig(
            enabled=db_data.get("enabled", True),
            url=db_data.get("url"),
            host=db_data.get("host", "localhost"),
            port=db_data.get("port", 5432),
            name=db_data.get("name", "openclaw"),
            user=db_data.get("user", "openclaw"),
            password=db_data.get("password"),
            pool_size=db_data.get("pool_size", 10),
            max_overflow=db_data.get("max_overflow", 20),
        )
        
        # Build logging config
        logging_data = data.get("logging", {})
        logging_config = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            format=logging_data.get("format", "structured"),
            log_file=logging_data.get("log_file", "./logs/arbitrage_hunter.log"),
            max_file_size_mb=logging_data.get("max_file_size_mb", 100),
            backup_count=logging_data.get("backup_count", 5),
            console_output=logging_data.get("console_output", True),
        )
        
        # Build audit config
        audit_data = data.get("audit_logging", {})
        audit = AuditConfig(
            enabled=audit_data.get("enabled", True),
            path=audit_data.get("path", "./logs/audit"),
        )
        
        # Build metrics config
        metrics_data = data.get("metrics", {})
        metrics = MetricsConfig(
            enabled=metrics_data.get("enabled", True),
            port=metrics_data.get("port", 9090),
        )
        
        # Build health check config
        health_data = data.get("health_check", {})
        health_check = HealthCheckConfig(
            enabled=health_data.get("enabled", True),
            interval_seconds=health_data.get("interval_seconds", 30),
        )
        
        # Build main config
        return Config(
            scan_interval_minutes=data.get("scan_interval_minutes", 5),
            min_profit_threshold=data.get("min_profit_threshold", 0.02),
            min_edge_percent=data.get("min_edge_percent", 2.0),
            min_profit_per_unit=data.get("min_profit_per_unit", 10.0),
            max_stake_per_leg=data.get("max_stake_per_leg", 1000.0),
            max_total_exposure=data.get("max_total_exposure", 5000.0),
            sports_to_scan=data.get("sports_to_scan", ["NBA", "NFL", "MLB", "NHL"]),
            telegram_enabled=data.get("telegram_enabled", True),
            telegram_bot_token=data.get("telegram_bot_token"),
            telegram_chat_id=data.get("telegram_chat_id"),
            top_n_alerts=data.get("top_n_alerts", 10),
            alert_high_priority_threshold=data.get("alert_high_priority_threshold", 5.0),
            alert_medium_priority_threshold=data.get("alert_medium_priority_threshold", 3.0),
            sources=sources,
            database=database,
            dry_run=data.get("dry_run", False),
            enabled=data.get("enabled", True),
            max_concurrent_requests=data.get("max_concurrent_requests", 10),
            request_delay_seconds=data.get("request_delay_seconds", 0.1),
            fetch_timeout_seconds=data.get("fetch_timeout_seconds", 30.0),
            total_scan_timeout_seconds=data.get("total_scan_timeout_seconds", 300.0),
            logging=logging_config,
            audit_logging=audit,
            metrics=metrics,
            health_check=health_check,
        )
    
    @classmethod
    def validate(cls, config: Config) -> tuple[bool, list[str]]:
        """
        Validate configuration and return (is_valid, errors).
        
        Args:
            config: Config instance to validate
        
        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors: list[str] = []
        
        # Validate thresholds
        if config.min_profit_threshold < 0:
            errors.append("min_profit_threshold must be non-negative")
        if config.min_edge_percent < 0:
            errors.append("min_edge_percent must be non-negative")
        if config.min_profit_per_unit < 0:
            errors.append("min_profit_per_unit must be non-negative")
        
        # Validate sports
        if not config.sports_to_scan:
            errors.append("sports_to_scan must contain at least one sport")
        
        # Validate sources
        enabled_sources = config.get_enabled_sources()
        if not enabled_sources:
            errors.append("At least one data source must be enabled")
        
        # Validate Telegram config
        if config.telegram_enabled:
            if not config.telegram_bot_token:
                errors.append("telegram_bot_token is required when telegram_enabled is true")
            if not config.telegram_chat_id:
                errors.append("telegram_chat_id is required when telegram_enabled is true")
        
        # Validate database
        if config.database.enabled and not config.database.get_url():
            errors.append("database URL is required when database is enabled")
        
        return len(errors) == 0, errors
