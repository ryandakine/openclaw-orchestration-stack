"""
Core Pydantic Settings for OpenClaw Arbitrage Hunter.

This module defines the main Settings class using pydantic-settings v2,
providing centralized configuration with environment variable support.
"""

from typing import Literal, Self
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Main application settings with environment variable support.
    
    All settings can be overridden via environment variables.
    Uses pydantic-settings v2 for validation and parsing.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        validate_assignment=True,
    )
    
    # =============================================================================
    # Application Settings
    # =============================================================================
    
    app_name: str = Field(
        default="OpenClaw Arbitrage Hunter",
        description="Application name for logging and identification",
    )
    
    app_version: str = Field(
        default="1.0.0",
        description="Application version string",
    )
    
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Runtime environment",
    )
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )
    
    # =============================================================================
    # Database Settings
    # =============================================================================
    
    database_url: str | None = Field(
        default=None,
        description="PostgreSQL connection URL. If not set, uses individual params",
    )
    
    db_host: str = Field(
        default="localhost",
        description="Database host",
    )
    
    db_port: int = Field(
        default=5432,
        description="Database port",
        ge=1,
        le=65535,
    )
    
    db_name: str = Field(
        default="openclaw",
        description="Database name",
    )
    
    db_user: str = Field(
        default="openclaw",
        description="Database user",
    )
    
    db_password: str = Field(
        default="",
        description="Database password",
    )
    
    db_pool_size: int = Field(
        default=10,
        description="Database connection pool size",
        ge=1,
        le=100,
    )
    
    db_max_overflow: int = Field(
        default=20,
        description="Max overflow connections beyond pool size",
        ge=0,
        le=100,
    )
    
    # =============================================================================
    # Redis Settings
    # =============================================================================
    
    redis_url: str | None = Field(
        default=None,
        description="Redis connection URL. If not set, uses individual params",
    )
    
    redis_host: str = Field(
        default="localhost",
        description="Redis host",
    )
    
    redis_port: int = Field(
        default=6379,
        description="Redis port",
        ge=1,
        le=65535,
    )
    
    redis_db: int = Field(
        default=0,
        description="Redis database number",
        ge=0,
        le=15,
    )
    
    redis_password: str | None = Field(
        default=None,
        description="Redis password (optional)",
    )
    
    # =============================================================================
    # API Settings
    # =============================================================================
    
    api_host: str = Field(
        default="0.0.0.0",
        description="API server bind host",
    )
    
    api_port: int = Field(
        default=8000,
        description="API server port",
        ge=1,
        le=65535,
    )
    
    api_workers: int = Field(
        default=1,
        description="Number of API worker processes",
        ge=1,
        le=16,
    )
    
    # =============================================================================
    # Arbitrage Engine Settings
    # =============================================================================
    
    arb_scan_interval_seconds: float = Field(
        default=5.0,
        description="Interval between arbitrage scans in seconds",
        ge=0.1,
        le=300.0,
    )
    
    arb_max_concurrent_scans: int = Field(
        default=10,
        description="Maximum concurrent arbitrage scans",
        ge=1,
        le=100,
    )
    
    arb_cache_ttl_seconds: int = Field(
        default=30,
        description="Cache TTL for arbitrage calculations in seconds",
        ge=1,
        le=3600,
    )
    
    # =============================================================================
    # Execution Settings
    # =============================================================================
    
    dry_run: bool = Field(
        default=True,
        description="Run in dry-run mode (no real trades)",
    )
    
    max_position_size_usd: float = Field(
        default=1000.0,
        description="Maximum position size in USD",
        ge=10.0,
        le=100000.0,
    )
    
    min_position_size_usd: float = Field(
        default=10.0,
        description="Minimum position size in USD",
        ge=1.0,
        le=1000.0,
    )
    
    # =============================================================================
    # Monitoring Settings
    # =============================================================================
    
    health_check_interval_seconds: int = Field(
        default=30,
        description="Health check interval in seconds",
        ge=5,
        le=300,
    )
    
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics",
    )
    
    metrics_port: int = Field(
        default=9090,
        description="Prometheus metrics port",
        ge=1,
        le=65535,
    )
    
    # =============================================================================
    # Validators
    # =============================================================================
    
    @field_validator("db_port", "redis_port", "api_port", "metrics_port", mode="before")
    @classmethod
    def parse_port_from_string(cls, v: str | int) -> int:
        """Parse port values that may come as strings from env vars."""
        if isinstance(v, str):
            return int(v)
        return v
    
    @model_validator(mode="after")
    def validate_position_sizes(self) -> Self:
        """Ensure min position size is less than max."""
        if self.min_position_size_usd >= self.max_position_size_usd:
            raise ValueError("min_position_size_usd must be less than max_position_size_usd")
        return self
    
    @model_validator(mode="after")
    def validate_database_url(self) -> Self:
        """Build database URL from individual params if not provided."""
        if self.database_url is None:
            password_part = f":{self.db_password}" if self.db_password else ""
            self.database_url = (
                f"postgresql://{self.db_user}{password_part}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self
    
    @model_validator(mode="after")
    def validate_redis_url(self) -> Self:
        """Build Redis URL from individual params if not provided."""
        if self.redis_url is None:
            password_part = f":{self.redis_password}@" if self.redis_password else ""
            self.redis_url = f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return self
    
    # =============================================================================
    # Properties
    # =============================================================================
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    @property
    def effective_log_level(self) -> str:
        """Get effective log level (DEBUG in dev unless overridden)."""
        if self.is_development and self.log_level == "INFO":
            return "DEBUG"
        return self.log_level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to avoid re-reading environment variables
    on every call during the application lifecycle.
    
    Returns:
        Settings: Cached settings instance
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Force reload settings from environment.
    
    Clears the cache and re-reads all environment variables.
    Useful for testing or when env vars change at runtime.
    
    Returns:
        Settings: Fresh settings instance
    """
    get_settings.cache_clear()
    return get_settings()
