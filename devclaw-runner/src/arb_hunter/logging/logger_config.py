"""
logger_config.py - Structlog configuration with JSON format, log levels, and rotation.

Provides centralized logging setup with structured JSON output, correlation ID support,
and automatic log rotation for production use.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from pythonjsonlogger import jsonlogger
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler


# Default log format with all structured fields
DEFAULT_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s %(message)s "
    "%(correlation_id)s %(event)s %(timestamp)s"
)

JSON_LOG_FORMAT = (
    "%(asctime) %(levelname) %(name) %(message) "
    "%(correlation_id) %(event) %(timestamp)"
)


class CorrelationIdFilter(logging.Filter):
    """Inject correlation ID into log records from context vars."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to log record from structlog context."""
        from structlog.contextvars import get_contextvars
        ctx = get_contextvars()
        record.correlation_id = ctx.get("correlation_id", "N/A")
        record.event = getattr(record, "event", "")
        record.timestamp = getattr(record, "timestamp", "")
        return True


def setup_structlog(
    log_level: str = "INFO",
    json_format: bool = True,
    service_name: str = "arb_hunter"
) -> None:
    """
    Configure structlog with JSON formatting and standard processors.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output JSON formatted logs
        service_name: Service identifier for all logs
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
    ]
    
    if json_format:
        # JSON formatting for production
        structlog.configure(
            processors=shared_processors + [
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
    else:
        # Pretty console formatting for development
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(
                    colors=True,
                    exception_formatter=structlog.dev.plain_traceback,
                ),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    # Set root logger level
    logging.getLogger().setLevel(getattr(logging, log_level.upper()))


def setup_file_handlers(
    log_dir: Path,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = True
) -> None:
    """
    Configure rotating file handlers for persistent logging.
    
    Args:
        log_dir: Directory to store log files
        max_bytes: Maximum bytes per log file before rotation
        backup_count: Number of backup files to keep
        json_format: Whether to use JSON formatting
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        if isinstance(handler, (RotatingFileHandler, TimedRotatingFileHandler)):
            root_logger.removeHandler(handler)
    
    # Main application log
    app_log_path = log_dir / "arb_hunter.log"
    app_handler = RotatingFileHandler(
        app_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    app_handler.addFilter(CorrelationIdFilter())
    
    if json_format:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(correlation_id)s %(event)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            }
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)
    
    # Error log (separate file for errors)
    error_log_path = log_dir / "errors.log"
    error_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(CorrelationIdFilter())
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)


def setup_console_handler(
    json_format: bool = False,
    log_level: str = "INFO"
) -> None:
    """
    Configure console output handler.
    
    Args:
        json_format: Whether to output JSON to console
        log_level: Minimum log level for console
    """
    root_logger = logging.getLogger()
    
    # Remove existing console handlers
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            root_logger.removeHandler(handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    if json_format:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def initialize_logging(
    log_dir: Optional[Path] = None,
    log_level: str = "INFO",
    json_format: bool = True,
    service_name: str = "arb_hunter",
    enable_console: bool = True,
    enable_file: bool = True
) -> structlog.stdlib.BoundLogger:
    """
    Initialize complete logging configuration.
    
    This is the main entry point for setting up logging in the application.
    
    Args:
        log_dir: Directory for log files (required if enable_file=True)
        log_level: Minimum log level
        json_format: Whether to use JSON formatting
        service_name: Service identifier
        enable_console: Whether to log to console
        enable_file: Whether to log to files
        
    Returns:
        Configured structlog logger instance
    """
    # Configure structlog processors
    setup_structlog(log_level=log_level, json_format=json_format, service_name=service_name)
    
    # Setup handlers
    if enable_console:
        setup_console_handler(json_format=json_format, log_level=log_level)
    
    if enable_file and log_dir:
        setup_file_handlers(log_dir=log_dir, json_format=json_format)
    
    # Get and configure the main logger
    logger = structlog.get_logger("arb_hunter")
    logger.info(
        "logging_initialized",
        service=service_name,
        log_level=log_level,
        json_format=json_format,
        log_dir=str(log_dir) if log_dir else None
    )
    
    return logger


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger by name."""
    return structlog.get_logger(name)


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in the context for the current execution."""
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Clear the correlation ID from the context."""
    structlog.contextvars.clear_contextvars()


def bind_context(**kwargs) -> None:
    """Bind additional context variables to all subsequent logs."""
    structlog.contextvars.bind_contextvars(**kwargs)
