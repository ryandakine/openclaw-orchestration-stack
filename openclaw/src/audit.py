"""
OpenClaw Audit Trail Integration

Provides comprehensive audit logging for all OpenClaw operations.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from contextvars import ContextVar

# Context variable for correlation ID
_correlation_id_ctx: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
_actor_ctx: ContextVar[str] = ContextVar('actor', default='openclaw')


class AuditLevel(str, Enum):
    """Audit log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEvent:
    """Represents a single audit event."""
    
    def __init__(
        self,
        correlation_id: str,
        actor: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        level: AuditLevel = AuditLevel.INFO,
        timestamp: Optional[datetime] = None
    ):
        self.id = f"audit_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
        self.correlation_id = correlation_id
        self.actor = actor
        self.action = action
        self.payload = payload or {}
        self.level = level
        self.timestamp = timestamp or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "actor": self.actor,
            "action": self.action,
            "payload": self.payload,
            "level": self.level.value,
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_db_record(self) -> Dict[str, Any]:
        """Convert to database record format."""
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "payload": json.dumps(self.payload) if self.payload else None
        }


class AuditBackend:
    """Abstract base class for audit backends."""
    
    async def log(self, event: AuditEvent) -> bool:
        """Log an audit event."""
        raise NotImplementedError
    
    async def query(
        self,
        correlation_id: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Query audit events."""
        raise NotImplementedError


class SQLiteAuditBackend(AuditBackend):
    """SQLite-based audit logging backend."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")
    
    async def log(self, event: AuditEvent) -> bool:
        """Log event to SQLite database."""
        try:
            # Import here to avoid circular imports
            from ...shared.db import insert
            
            record = event.to_db_record()
            insert("audit_events", record)
            return True
        except Exception as e:
            print(f"Failed to log audit event: {e}")
            return False
    
    async def query(
        self,
        correlation_id: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Query events from SQLite database."""
        from ...shared.db import execute
        
        conditions = []
        params = []
        
        if correlation_id:
            conditions.append("correlation_id = ?")
            params.append(correlation_id)
        
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        
        if action:
            conditions.append("action = ?")
            params.append(action)
        
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())
        
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT * FROM audit_events 
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = execute(query, tuple(params))
        
        events = []
        for row in rows:
            events.append(AuditEvent(
                correlation_id=row["correlation_id"],
                actor=row["actor"],
                action=row["action"],
                payload=json.loads(row["payload"]) if row["payload"] else None,
                timestamp=datetime.fromisoformat(row["timestamp"])
            ))
        
        return events


class ConsoleAuditBackend(AuditBackend):
    """Console-based audit logging (for development)."""
    
    def __init__(self, colorize: bool = True):
        self.colorize = colorize
        self._colors = {
            AuditLevel.DEBUG: "\033[36m",      # Cyan
            AuditLevel.INFO: "\033[32m",       # Green
            AuditLevel.WARNING: "\033[33m",    # Yellow
            AuditLevel.ERROR: "\033[31m",      # Red
            AuditLevel.CRITICAL: "\033[35m",   # Magenta
            "reset": "\033[0m"
        }
    
    async def log(self, event: AuditEvent) -> bool:
        """Log event to console."""
        color = self._colors.get(event.level, "") if self.colorize else ""
        reset = self._colors["reset"] if self.colorize else ""
        
        print(f"{color}[AUDIT] {event.timestamp.isoformat()} | "
              f"{event.correlation_id} | {event.actor} | {event.action}{reset}")
        
        if event.payload:
            print(f"  Payload: {json.dumps(event.payload, indent=2)}")
        
        return True
    
    async def query(self, **kwargs) -> List[AuditEvent]:
        """Query not supported for console backend."""
        raise NotImplementedError("Query not supported for console backend")


class FileAuditBackend(AuditBackend):
    """File-based audit logging."""
    
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or os.environ.get(
            "AUDIT_LOG_PATH", 
            "data/audit.log"
        )
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
    
    async def log(self, event: AuditEvent) -> bool:
        """Log event to file."""
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
            return True
        except Exception as e:
            print(f"Failed to write audit log: {e}")
            return False
    
    async def query(
        self,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> List[AuditEvent]:
        """Query events from log file."""
        events = []
        
        try:
            with open(self.log_path, "r") as f:
                for line in f:
                    data = json.loads(line.strip())
                    
                    if correlation_id and data.get("correlation_id") != correlation_id:
                        continue
                    
                    events.append(AuditEvent(
                        correlation_id=data["correlation_id"],
                        actor=data["actor"],
                        action=data["action"],
                        payload=data.get("payload"),
                        level=AuditLevel(data.get("level", "info")),
                        timestamp=datetime.fromisoformat(data["timestamp"])
                    ))
        except FileNotFoundError:
            pass
        
        return events


class MultiBackend(AuditBackend):
    """Combines multiple backends."""
    
    def __init__(self, backends: List[AuditBackend]):
        self.backends = backends
    
    async def log(self, event: AuditEvent) -> bool:
        """Log to all backends."""
        results = await asyncio.gather(
            *[backend.log(event) for backend in self.backends],
            return_exceptions=True
        )
        return all(isinstance(r, bool) and r for r in results)
    
    async def query(self, **kwargs) -> List[AuditEvent]:
        """Query from first backend that supports it."""
        for backend in self.backends:
            try:
                return await backend.query(**kwargs)
            except NotImplementedError:
                continue
        return []


class AuditLogger:
    """Main audit logger class."""
    
    def __init__(self, backend: Optional[AuditBackend] = None):
        self.backend = backend or self._create_default_backend()
        self._middleware: List[Callable[[AuditEvent], AuditEvent]] = []
    
    def _create_default_backend(self) -> AuditBackend:
        """Create default backend based on environment."""
        # Check environment for backend preference
        backend_type = os.environ.get("AUDIT_BACKEND", "sqlite")
        
        if backend_type == "sqlite":
            return SQLiteAuditBackend()
        elif backend_type == "console":
            return ConsoleAuditBackend()
        elif backend_type == "file":
            return FileAuditBackend()
        elif backend_type == "multi":
            return MultiBackend([
                SQLiteAuditBackend(),
                ConsoleAuditBackend()
            ])
        else:
            return SQLiteAuditBackend()
    
    def add_middleware(self, middleware: Callable[[AuditEvent], AuditEvent]):
        """Add middleware to process events before logging."""
        self._middleware.append(middleware)
    
    async def log(
        self,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        level: AuditLevel = AuditLevel.INFO,
        correlation_id: Optional[str] = None,
        actor: Optional[str] = None
    ) -> bool:
        """
        Log an audit event.
        
        Args:
            action: The action being performed
            payload: Additional data about the action
            level: Severity level
            correlation_id: Optional correlation ID (uses context if not provided)
            actor: Optional actor name (uses context if not provided)
        
        Returns:
            True if logged successfully
        """
        # Use context vars if not provided
        corr_id = correlation_id or _correlation_id_ctx.get() or f"corr_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        act = actor or _actor_ctx.get()
        
        event = AuditEvent(
            correlation_id=corr_id,
            actor=act,
            action=action,
            payload=payload,
            level=level
        )
        
        # Apply middleware
        for mw in self._middleware:
            event = mw(event)
        
        return await self.backend.log(event)
    
    async def query(self, **kwargs) -> List[AuditEvent]:
        """Query audit events."""
        return await self.backend.query(**kwargs)
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current context."""
        _correlation_id_ctx.set(correlation_id)
    
    def set_actor(self, actor: str):
        """Set actor for current context."""
        _actor_ctx.set(actor)


# Global logger instance
_logger: Optional[AuditLogger] = None


def get_logger() -> AuditLogger:
    """Get or create the global audit logger."""
    global _logger
    if _logger is None:
        _logger = AuditLogger()
    return _logger


def configure_logger(backend: AuditBackend):
    """Configure the global logger with a specific backend."""
    global _logger
    _logger = AuditLogger(backend)
    return _logger


# Convenience functions

async def log_audit_event(
    correlation_id: str,
    actor: str,
    action: str,
    payload: Optional[Dict[str, Any]] = None,
    level: AuditLevel = AuditLevel.INFO
) -> bool:
    """
    Log an audit event.
    
    This is the main convenience function for audit logging.
    
    Args:
        correlation_id: Groups related events
        actor: Entity performing the action
        action: Action being performed
        payload: Additional event data
        level: Severity level
    
    Returns:
        True if logged successfully
    """
    logger = get_logger()
    return await logger.log(
        action=action,
        payload=payload,
        level=level,
        correlation_id=correlation_id,
        actor=actor
    )


async def get_audit_trail(
    correlation_id: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get the complete audit trail for a correlation ID.
    
    Args:
        correlation_id: The correlation ID to query
        limit: Maximum number of events to return
    
    Returns:
        List of audit events as dictionaries
    """
    logger = get_logger()
    events = await logger.query(correlation_id=correlation_id, limit=limit)
    return [e.to_dict() for e in events]


def with_audit_context(correlation_id: str, actor: str = "openclaw"):
    """
    Decorator to set audit context for a function.
    
    Usage:
        @with_audit_context("corr_123", "devclaw")
        async def process_task():
            await log_audit_event(...)  # Uses context correlation_id and actor
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            token_corr = _correlation_id_ctx.set(correlation_id)
            token_actor = _actor_ctx.set(actor)
            
            try:
                return await func(*args, **kwargs)
            finally:
                _correlation_id_ctx.reset(token_corr)
                _actor_ctx.reset(token_actor)
        
        return wrapper
    return decorator


class AuditContext:
    """Context manager for audit context."""
    
    def __init__(self, correlation_id: str, actor: str = "openclaw"):
        self.correlation_id = correlation_id
        self.actor = actor
        self._tokens = []
    
    async def __aenter__(self):
        self._tokens.append(_correlation_id_ctx.set(self.correlation_id))
        self._tokens.append(_actor_ctx.set(self.actor))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for token in reversed(self._tokens):
            if token:
                # Reset the appropriate context var
                if token == self._tokens[0]:
                    _correlation_id_ctx.reset(token)
                else:
                    _actor_ctx.reset(token)


# Common audit actions

class AuditActions:
    """Standard audit action names."""
    
    # Request lifecycle
    REQUEST_RECEIVED = "request_received"
    REQUEST_VALIDATED = "request_validated"
    REQUEST_REJECTED = "request_rejected"
    
    # Routing
    INTENT_CLASSIFIED = "intent_classified"
    ROUTING_DECISION = "routing_decision"
    ROUTING_FAILED = "routing_failed"
    
    # Action plans
    ACTION_PLAN_CREATED = "action_plan_created"
    ACTION_PLAN_EMITTED = "action_plan_emitted"
    ACTION_PLAN_FAILED = "action_plan_failed"
    
    # Task lifecycle
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRY_SCHEDULED = "task_retry_scheduled"
    
    # Reviews
    REVIEW_REQUESTED = "review_requested"
    REVIEW_COMPLETED = "review_completed"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    
    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIG_RELOADED = "config_reloaded"
