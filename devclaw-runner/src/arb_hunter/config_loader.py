"""
Configuration loader module.

Loads configuration from environment variables for the arb hunter.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Config:
    """Immutable configuration container for arb hunter."""

    # Feature flags
    enabled: bool = True

    # Thresholds
    min_edge_percent: float = 2.0
    min_profit_per_unit: float = 10.0
    max_stake_per_leg: float = 1000.0
    max_total_exposure: float = 5000.0

    # Ranking
    top_n_alerts: int = 10

    # API Keys (loaded from env)
    polymarket_api_key: str | None = None
    polymarket_api_secret: str | None = None

    # Sportsbook API credentials
    draftkings_api_key: str | None = None
    fanduel_api_key: str | None = None
    betmgm_api_key: str | None = None
    caesars_api_key: str | None = None

    # Alerting
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Audit logging
    audit_log_path: Path = field(default_factory=lambda: Path("./logs/audit"))
    enable_audit_logging: bool = True

    # Timeouts
    fetch_timeout_seconds: float = 30.0
    total_scan_timeout_seconds: float = 300.0

    # Rate limiting
    max_concurrent_requests: int = 10
    request_delay_seconds: float = 0.1

    def is_sportsbook_enabled(self, book_name: str) -> bool:
        """Check if a specific sportsbook API is configured."""
        key_mapping = {
            "draftkings": self.draftkings_api_key,
            "fanduel": self.fanduel_api_key,
            "betmgm": self.betmgm_api_key,
            "caesars": self.caesars_api_key,
        }
        return key_mapping.get(book_name.lower()) is not None

    def get_enabled_sportsbooks(self) -> list[str]:
        """Return list of enabled sportsbook names."""
        books = []
        for name in ["draftkings", "fanduel", "betmgm", "caesars"]:
            if self.is_sportsbook_enabled(name):
                books.append(name)
        return books


class ConfigLoader:
    """Loads configuration from environment variables."""

    ENV_PREFIX = "ARB_HUNTER_"

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        log = logger.bind(method="from_env")
        log.info("loading_configuration_from_env")

        def get_env(key: str, default: str | None = None, required: bool = False) -> str | None:
            """Helper to get environment variable with optional default."""
            full_key = f"{cls.ENV_PREFIX}{key}"
            value = os.getenv(full_key, default)
            if required and not value:
                raise ValueError(f"Required environment variable {full_key} is not set")
            if value:
                log.debug("env_var_loaded", key=full_key, has_value=True)
            return value

        def get_env_bool(key: str, default: bool = False) -> bool:
            """Helper to get boolean environment variable."""
            value = get_env(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")

        def get_env_float(key: str, default: float = 0.0) -> float:
            """Helper to get float environment variable."""
            value = get_env(key)
            if value is None:
                return default
            try:
                return float(value)
            except ValueError as e:
                log.warning("invalid_float_env", key=key, value=value, error=str(e))
                return default

        def get_env_int(key: str, default: int = 0) -> int:
            """Helper to get integer environment variable."""
            value = get_env(key)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError as e:
                log.warning("invalid_int_env", key=key, value=value, error=str(e))
                return default

        def get_env_path(key: str, default: Path | None = None) -> Path:
            """Helper to get path environment variable."""
            value = get_env(key)
            if value is None:
                return default or Path("./logs/audit")
            return Path(value)

        config = Config(
            enabled=get_env_bool("ENABLED", default=True),
            min_edge_percent=get_env_float("MIN_EDGE_PERCENT", default=2.0),
            min_profit_per_unit=get_env_float("MIN_PROFIT_PER_UNIT", default=10.0),
            max_stake_per_leg=get_env_float("MAX_STAKE_PER_LEG", default=1000.0),
            max_total_exposure=get_env_float("MAX_TOTAL_EXPOSURE", default=5000.0),
            top_n_alerts=get_env_int("TOP_N_ALERTS", default=10),
            polymarket_api_key=get_env("POLYMARKET_API_KEY"),
            polymarket_api_secret=get_env("POLYMARKET_API_SECRET"),
            draftkings_api_key=get_env("DRAFTKINGS_API_KEY"),
            fanduel_api_key=get_env("FANDUEL_API_KEY"),
            betmgm_api_key=get_env("BETMGM_API_KEY"),
            caesars_api_key=get_env("CAESARS_API_KEY"),
            telegram_bot_token=get_env("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=get_env("TELEGRAM_CHAT_ID"),
            audit_log_path=get_env_path("AUDIT_LOG_PATH", default=Path("./logs/audit")),
            enable_audit_logging=get_env_bool("ENABLE_AUDIT_LOGGING", default=True),
            fetch_timeout_seconds=get_env_float("FETCH_TIMEOUT_SECONDS", default=30.0),
            total_scan_timeout_seconds=get_env_float("TOTAL_SCAN_TIMEOUT_SECONDS", default=300.0),
            max_concurrent_requests=get_env_int("MAX_CONCURRENT_REQUESTS", default=10),
            request_delay_seconds=get_env_float("REQUEST_DELAY_SECONDS", default=0.1),
        )

        log.info(
            "configuration_loaded",
            enabled=config.enabled,
            min_edge=config.min_edge_percent,
            top_n=config.top_n_alerts,
            enabled_sportsbooks=config.get_enabled_sportsbooks(),
        )

        return config

    @classmethod
    def from_dict(cls, config_dict: dict) -> Config:
        """Load configuration from a dictionary (useful for testing)."""
        log = logger.bind(method="from_dict")
        log.info("loading_configuration_from_dict")

        config = Config(
            enabled=config_dict.get("enabled", True),
            min_edge_percent=float(config_dict.get("min_edge_percent", 2.0)),
            min_profit_per_unit=float(config_dict.get("min_profit_per_unit", 10.0)),
            max_stake_per_leg=float(config_dict.get("max_stake_per_leg", 1000.0)),
            max_total_exposure=float(config_dict.get("max_total_exposure", 5000.0)),
            top_n_alerts=int(config_dict.get("top_n_alerts", 10)),
            polymarket_api_key=config_dict.get("polymarket_api_key"),
            polymarket_api_secret=config_dict.get("polymarket_api_secret"),
            draftkings_api_key=config_dict.get("draftkings_api_key"),
            fanduel_api_key=config_dict.get("fanduel_api_key"),
            betmgm_api_key=config_dict.get("betmgm_api_key"),
            caesars_api_key=config_dict.get("caesars_api_key"),
            telegram_bot_token=config_dict.get("telegram_bot_token"),
            telegram_chat_id=config_dict.get("telegram_chat_id"),
            audit_log_path=Path(config_dict.get("audit_log_path", "./logs/audit")),
            enable_audit_logging=config_dict.get("enable_audit_logging", True),
            fetch_timeout_seconds=float(config_dict.get("fetch_timeout_seconds", 30.0)),
            total_scan_timeout_seconds=float(config_dict.get("total_scan_timeout_seconds", 300.0)),
            max_concurrent_requests=int(config_dict.get("max_concurrent_requests", 10)),
            request_delay_seconds=float(config_dict.get("request_delay_seconds", 0.1)),
        )

        log.info("configuration_loaded_from_dict")
        return config

    @classmethod
    def validate(cls, config: Config) -> tuple[bool, list[str]]:
        """Validate configuration and return (is_valid, list_of_errors)."""
        errors: list[str] = []

        if config.min_edge_percent < 0:
            errors.append("min_edge_percent must be non-negative")

        if config.min_profit_per_unit < 0:
            errors.append("min_profit_per_profit_per_unit must be non-negative")

        if config.top_n_alerts < 1:
            errors.append("top_n_alerts must be at least 1")

        if config.max_concurrent_requests < 1:
            errors.append("max_concurrent_requests must be at least 1")

        if not config.polymarket_api_key:
            errors.append("polymarket_api_key is required")

        if not config.get_enabled_sportsbooks():
            errors.append("at least one sportsbook API key is required")

        if config.telegram_bot_token and not config.telegram_chat_id:
            errors.append("telegram_chat_id is required when telegram_bot_token is set")

        return len(errors) == 0, errors
