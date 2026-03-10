"""
OpenClaw ActionPlan Emitter

Emits action plans to the appropriate message queues, webhooks, or workers.
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum
import aiohttp

from ..schemas.action_plan import ActionPlan, WorkerType, TaskStatus


class EmitterBackend(str, Enum):
    """Available emitter backends."""
    WEBHOOK = "webhook"
    RABBITMQ = "rabbitmq"
    REDIS = "redis"
    SQLITE_QUEUE = "sqlite_queue"
    CONSOLE = "console"


class EmitError(Exception):
    """Raised when emission fails."""
    pass


class Emitter:
    """
    Emits action plans to configured destinations.
    
    Supports multiple backends: webhook, message queues, database.
    """
    
    def __init__(self, backend: Optional[EmitterBackend] = None):
        self.backend = backend or self._detect_backend()
        self._handlers: Dict[WorkerType, List[Callable]] = {
            WorkerType.DEVCLAW: [],
            WorkerType.SYMPHONY: []
        }
        self._webhook_urls: Dict[WorkerType, Optional[str]] = {
            WorkerType.DEVCLAW: os.environ.get("DEVCLAW_WEBHOOK_URL"),
            WorkerType.SYMPHONY: os.environ.get("SYMPHONY_WEBHOOK_URL")
        }
    
    def _detect_backend(self) -> EmitterBackend:
        """Detect which backend to use based on environment."""
        if os.environ.get("RABBITMQ_URL"):
            return EmitterBackend.RABBITMQ
        elif os.environ.get("REDIS_URL"):
            return EmitterBackend.REDIS
        elif os.environ.get("WEBHOOK_URL"):
            return EmitterBackend.WEBHOOK
        else:
            return EmitterBackend.SQLITE_QUEUE
    
    def register_handler(self, worker_type: WorkerType, handler: Callable):
        """
        Register a custom handler for a worker type.
        
        Args:
            worker_type: The worker type to handle
            handler: Async function that receives the action plan
        """
        self._handlers[worker_type].append(handler)
    
    async def emit(self, plan: ActionPlan) -> Dict[str, Any]:
        """
        Emit an action plan to the appropriate destination.
        
        Args:
            plan: The action plan to emit
        
        Returns:
            Emission result with status and details
        """
        worker_type = plan.routing.worker_type
        
        result = {
            "plan_id": plan.plan_id,
            "worker_type": worker_type.value,
            "backend": self.backend.value,
            "emitted_at": datetime.utcnow().isoformat(),
            "success": False,
            "details": {}
        }
        
        try:
            # Call custom handlers first
            for handler in self._handlers[worker_type]:
                await handler(plan)
            
            # Then use configured backend
            if self.backend == EmitterBackend.WEBHOOK:
                await self._emit_webhook(plan, result)
            elif self.backend == EmitterBackend.RABBITMQ:
                await self._emit_rabbitmq(plan, result)
            elif self.backend == EmitterBackend.REDIS:
                await self._emit_redis(plan, result)
            elif self.backend == EmitterBackend.SQLITE_QUEUE:
                await self._emit_sqlite(plan, result)
            elif self.backend == EmitterBackend.CONSOLE:
                await self._emit_console(plan, result)
            
            result["success"] = True
            
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            raise EmitError(f"Failed to emit plan {plan.plan_id}: {e}") from e
        
        return result
    
    async def _emit_webhook(self, plan: ActionPlan, result: Dict[str, Any]):
        """Emit via HTTP webhook."""
        worker_type = plan.routing.worker_type
        webhook_url = self._webhook_urls.get(worker_type)
        
        if not webhook_url:
            raise EmitError(f"No webhook URL configured for {worker_type.value}")
        
        payload = {
            "event": "action_plan_created",
            "timestamp": datetime.utcnow().isoformat(),
            "plan": plan.dict()
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                result["details"]["status_code"] = response.status
                result["details"]["webhook_url"] = webhook_url
    
    async def _emit_rabbitmq(self, plan: ActionPlan, result: Dict[str, Any]):
        """Emit via RabbitMQ message queue."""
        try:
            import pika
            
            rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://localhost")
            queue_name = f"openclaw_{plan.routing.worker_type.value.lower()}"
            
            # Parse URL
            params = pika.URLParameters(rabbitmq_url)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            
            # Declare queue
            channel.queue_declare(queue=queue_name, durable=True)
            
            # Publish message
            message = json.dumps({
                "plan_id": plan.plan_id,
                "correlation_id": plan.correlation_id,
                "worker_type": plan.routing.worker_type.value,
                "action_type": plan.routing.action_type.value,
                "payload": plan.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=message.encode(),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type="application/json",
                    correlation_id=plan.correlation_id
                )
            )
            
            connection.close()
            
            result["details"]["queue"] = queue_name
            result["details"]["message_size"] = len(message)
            
        except ImportError:
            raise EmitError("pika package required for RabbitMQ backend")
    
    async def _emit_redis(self, plan: ActionPlan, result: Dict[str, Any]):
        """Emit via Redis stream or list."""
        try:
            import redis.asyncio as redis
            
            redis_url = os.environ.get("REDIS_URL", "redis://localhost")
            stream_key = f"openclaw:{plan.routing.worker_type.value.lower()}:queue"
            
            r = redis.from_url(redis_url)
            
            message = {
                "plan_id": plan.plan_id,
                "correlation_id": plan.correlation_id,
                "worker_type": plan.routing.worker_type.value,
                "action_type": plan.routing.action_type.value,
                "payload": json.dumps(plan.dict()),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add to stream
            await r.xadd(stream_key, message)
            await r.close()
            
            result["details"]["stream"] = stream_key
            
        except ImportError:
            raise EmitError("redis package required for Redis backend")
    
    async def _emit_sqlite(self, plan: ActionPlan, result: Dict[str, Any]):
        """Emit via SQLite task queue (default for local development)."""
        from ...shared.db import insert
        
        task_data = {
            "id": plan.plan_id,
            "correlation_id": plan.correlation_id,
            "status": TaskStatus.QUEUED.value,
            "assigned_to": plan.routing.worker_type.value,
            "payload": json.dumps(plan.dict()),
            "created_at": datetime.utcnow().isoformat()
        }
        
        insert("tasks", task_data)
        
        result["details"]["table"] = "tasks"
        result["details"]["task_id"] = plan.plan_id
    
    async def _emit_console(self, plan: ActionPlan, result: Dict[str, Any]):
        """Emit to console (for debugging)."""
        print("\n" + "=" * 60)
        print(f"📋 ACTION PLAN EMITTED")
        print("=" * 60)
        print(f"Plan ID: {plan.plan_id}")
        print(f"Correlation ID: {plan.correlation_id}")
        print(f"Worker: {plan.routing.worker_type.value}")
        print(f"Action: {plan.routing.action_type.value}")
        print(f"Confidence: {plan.routing.confidence:.2f}")
        print(f"Requires Review: {plan.routing.requires_review}")
        print(f"Priority: {plan.routing.priority}")
        print("-" * 60)
        print(json.dumps(plan.dict(), indent=2, default=str))
        print("=" * 60 + "\n")
        
        result["details"]["output"] = "console"


# Global emitter instance
_emitter: Optional[Emitter] = None


def get_emitter() -> Emitter:
    """Get or create the global emitter instance."""
    global _emitter
    if _emitter is None:
        _emitter = Emitter()
    return _emitter


def configure_emitter(backend: EmitterBackend):
    """Configure the global emitter with a specific backend."""
    global _emitter
    _emitter = Emitter(backend)
    return _emitter


async def emit_action_plan(plan: ActionPlan) -> Dict[str, Any]:
    """
    Convenience function to emit an action plan.
    
    Args:
        plan: The action plan to emit
    
    Returns:
        Emission result
    """
    emitter = get_emitter()
    return await emitter.emit(plan)


async def emit_batch(plans: List[ActionPlan]) -> List[Dict[str, Any]]:
    """
    Emit multiple action plans.
    
    Args:
        plans: List of action plans to emit
    
    Returns:
        List of emission results
    """
    emitter = get_emitter()
    results = []
    
    for plan in plans:
        result = await emitter.emit(plan)
        results.append(result)
    
    return results


class ActionPlanSubscription:
    """
    Subscribe to action plans for a specific worker.
    
    Usage:
        async with ActionPlanSubscription(WorkerType.DEVCLAW) as sub:
            async for plan in sub:
                process_plan(plan)
    """
    
    def __init__(self, worker_type: WorkerType, backend: Optional[EmitterBackend] = None):
        self.worker_type = worker_type
        self.backend = backend or EmitterBackend.SQLITE_QUEUE
        self._running = False
    
    async def __aenter__(self):
        self._running = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._running = False
    
    async def __aiter__(self):
        """Async iterator for receiving plans."""
        if self.backend == EmitterBackend.SQLITE_QUEUE:
            async for plan in self._sqlite_iterator():
                yield plan
        elif self.backend == EmitterBackend.REDIS:
            async for plan in self._redis_iterator():
                yield plan
        else:
            raise EmitError(f"Subscription not supported for {self.backend}")
    
    async def _sqlite_iterator(self):
        """Iterate over pending tasks from SQLite."""
        from ...shared.db import execute, update
        
        while self._running:
            # Get pending tasks for this worker
            tasks = execute(
                """
                SELECT * FROM tasks 
                WHERE assigned_to = ? AND status = 'queued'
                AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'))
                ORDER BY created_at
                LIMIT 1
                """,
                (self.worker_type.value,)
            )
            
            if tasks:
                task = tasks[0]
                
                # Claim the task
                update(
                    "tasks",
                    {
                        "status": "executing",
                        "claimed_by": "worker_instance",
                        "claimed_at": datetime.utcnow().isoformat()
                    },
                    "id = ?",
                    (task["id"],)
                )
                
                # Parse and yield plan
                plan_data = json.loads(task["payload"])
                yield ActionPlan(**plan_data)
            else:
                # No tasks available, wait before checking again
                await asyncio.sleep(1)
    
    async def _redis_iterator(self):
        """Iterate over messages from Redis stream."""
        try:
            import redis.asyncio as redis
            
            redis_url = os.environ.get("REDIS_URL", "redis://localhost")
            stream_key = f"openclaw:{self.worker_type.value.lower()}:queue"
            consumer_group = f"{self.worker_type.value.lower()}_workers"
            consumer_name = f"worker_{os.getpid()}"
            
            r = redis.from_url(redis_url)
            
            # Create consumer group
            try:
                await r.xgroup_create(stream_key, consumer_group, id="0", mkstream=True)
            except redis.ResponseError:
                pass  # Group already exists
            
            while self._running:
                # Read from stream
                messages = await r.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream_key: ">"},
                    count=1,
                    block=5000
                )
                
                if messages:
                    for stream, msgs in messages:
                        for msg_id, fields in msgs:
                            # Parse message
                            payload = json.loads(fields.get("payload", "{}"))
                            yield ActionPlan(**payload)
                            
                            # Acknowledge message
                            await r.xack(stream_key, consumer_group, msg_id)
                
                await asyncio.sleep(0.1)
            
            await r.close()
            
        except ImportError:
            raise EmitError("redis package required for Redis backend")
