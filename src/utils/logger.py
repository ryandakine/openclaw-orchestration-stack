"""
Structured logging module for the Sportsbook/Arbitrage Hunter.

Provides consistent, timestamped logging with both structured (JSON) and
human-readable formats. Supports file and console output with rotation.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class StructuredLogFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs.
    
    Includes timestamp, log level, logger name, message, and any extra fields.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add any extra fields from the record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "asctime", "getMessage"
            ):
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


class ColoredConsoleFormatter(logging.Formatter):
    """
    Formatter for colored console output.
    
    Uses ANSI color codes for different log levels.
    """
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",      # Reset
    }
    
    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt, datefmt)
        self.use_colors = sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        if self.use_colors:
            color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            reset = self.COLORS["RESET"]
            record.levelname = f"{color}{record.levelname}{reset}"
        
        return super().format(record)


class LoggerAdapter:
    """
    Adapter that adds context to log messages.
    
    Similar to structlog, this allows binding context that will be included
    in all subsequent log messages. Context is passed via the 'extra' dict.
    """
    
    def __init__(self, logger: logging.Logger, context: dict[str, Any] | None = None):
        self.logger = logger
        self.context = context or {}
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """Log with context added to extra."""
        # Build extra dict from context and kwargs
        extra = dict(self.context)  # Copy context
        for key, value in kwargs.items():
            extra[key] = value
        
        if extra:
            self.logger.log(level, msg, *args, extra=extra)
        else:
            self.logger.log(level, msg, *args)
    
    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log an exception with traceback."""
        extra = dict(self.context)
        for key, value in kwargs.items():
            extra[key] = value
        extra["exc_info"] = True
        self.logger.exception(msg, *args, extra=extra)
    
    def bind(self, **kwargs) -> "LoggerAdapter":
        """Create a new adapter with additional context."""
        new_context = {**self.context, **kwargs}
        return LoggerAdapter(self.logger, new_context)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = "./logs/arbitrage_hunter.log",
    format_type: str = "structured",
    max_file_size_mb: int = 100,
    backup_count: int = 5,
    console_output: bool = True,
) -> logging.Logger:
    """
    Configure the logging system.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None to disable file logging)
        format_type: "structured" for JSON, "simple" for human-readable
        max_file_size_mb: Maximum log file size before rotation
        backup_count: Number of backup files to keep
        console_output: Whether to output to console
    
    Returns:
        Configured root logger instance
    """
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get root logger for this application
    logger = logging.getLogger("arbitrage_hunter")
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers = []  # Clear existing handlers
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        
        if format_type == "structured":
            console_handler.setFormatter(StructuredLogFormatter())
        else:
            console_handler.setFormatter(ColoredConsoleFormatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
        
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> LoggerAdapter:
    """
    Get a logger instance with the given name.
    
    The logger will be a child of the main "arbitrage_hunter" logger.
    Returns a LoggerAdapter that supports structured logging with kwargs.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        LoggerAdapter instance
    """
    logger = logging.getLogger(f"arbitrage_hunter.{name}")
    return LoggerAdapter(logger, {})
