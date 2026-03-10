"""
OpenClaw Conductor - The orchestration brain that routes work.
Minimizes token usage by focusing on routing decisions only.
"""
import json
import uuid
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


class Intent(Enum):
    """Supported action intents."""
    PR_FIX = "PR_FIX"
    CODE_CHANGE = "CODE_CHANGE"
    FILE_TASK = "FILE_TASK"
    DB_READ = "DB_READ"
    DB_UPDATE = "DB_UPDATE"
    NOTIFY = "NOTIFY"
    CMS_EDIT = "CMS_EDIT"


class RouteTarget(Enum):
    """Target destinations for routed work."""
    SYMPHONY = "SYMPHONY"
    DEVCLAW = "DEVCLAW"
    N8N = "N8N"
    MCP_DB = "MCP_DB"
    MCP_CMS = "MCP_CMS"


@dataclass
class ActionPlan:
    """
    Structured action plan produced by OpenClaw.
    This is the output format for all routing decisions.
    """
    action_id: str
    correlation_id: str
    idempotency_key: str
    route_to: str
    intent: str
    payload: Dict[str, Any]
    audit: Dict[str, Any]
    
    @classmethod
    def create(
        cls,
        route_to: RouteTarget,
        intent: Intent,
        payload: Dict[str, Any],
        requested_by: str = "system",
        source: str = "api",
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> "ActionPlan":
        """Factory method to create a new ActionPlan."""
        return cls(
            action_id=str(uuid.uuid4()),
            correlation_id=correlation_id or str(uuid.uuid4()),
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            route_to=route_to.value,
            intent=intent.value,
            payload=payload,
            audit={
                "requested_by": requested_by,
                "source": source,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class OpenClawConductor:
    """
    The orchestration brain. Receives requests and routes work.
    
    Design principles:
    - Minimize token usage (don't do work, just route)
    - Single responsibility: decision making
    - Stateless: all state in database
    - Idempotent: same input = same routing decision
    """
    
    # Intent to target mapping
    INTENT_ROUTES = {
        Intent.PR_FIX: RouteTarget.SYMPHONY,
        Intent.CODE_CHANGE: RouteTarget.DEVCLAW,
        Intent.FILE_TASK: RouteTarget.DEVCLAW,
        Intent.DB_READ: RouteTarget.MCP_DB,
        Intent.DB_UPDATE: RouteTarget.MCP_DB,
        Intent.NOTIFY: RouteTarget.N8N,
        Intent.CMS_EDIT: RouteTarget.MCP_CMS,
    }
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
    
    def process_request(
        self,
        request: Dict[str, Any],
        requested_by: str = "system",
        source: str = "api"
    ) -> ActionPlan:
        """
        Process an incoming request and produce an ActionPlan.
        
        Args:
            request: Dictionary containing 'intent' and 'payload'
            requested_by: Identifier of who/what made the request
            source: Source system (chat, github_pr, github_issue, cron, api)
        
        Returns:
            ActionPlan with routing decision
        """
        # Extract intent
        intent_str = request.get("intent", "CODE_CHANGE")
        try:
            intent = Intent(intent_str)
        except ValueError:
            # Default to CODE_CHANGE for unknown intents
            intent = Intent.CODE_CHANGE
        
        # Determine routing target
        route_to = self._route_intent(intent)
        
        # Check idempotency if key provided
        idempotency_key = request.get("idempotency_key")
        if idempotency_key and self.db_manager:
            existing = self._check_idempotency(idempotency_key)
            if existing:
                return existing
        
        # Create action plan
        plan = ActionPlan.create(
            route_to=route_to,
            intent=intent,
            payload=request.get("payload", {}),
            requested_by=requested_by,
            source=source,
            correlation_id=request.get("correlation_id"),
            idempotency_key=idempotency_key
        )
        
        # Log to audit
        self._log_audit(plan)
        
        return plan
    
    def _route_intent(self, intent: Intent) -> RouteTarget:
        """Determine routing target based on intent."""
        return self.INTENT_ROUTES.get(intent, RouteTarget.DEVCLAW)
    
    def _check_idempotency(self, key: str) -> Optional[ActionPlan]:
        """Check if this request was already processed."""
        if not self.db_manager:
            return None
        
        result = self.db_manager.fetch_one(
            "SELECT response FROM idempotency_keys WHERE key = ?",
            (key,)
        )
        
        if result and result['response']:
            data = json.loads(result['response'])
            return ActionPlan(**data)
        return None
    
    def _log_audit(self, plan: ActionPlan):
        """Log routing decision to audit trail."""
        if not self.db_manager:
            return
        
        self.db_manager.execute(
            """INSERT INTO audit_events 
               (correlation_id, actor, action, payload)
               VALUES (?, ?, ?, ?)""",
            (
                plan.correlation_id,
                "openclaw",
                f"action_plan.created",
                plan.to_json()
            )
        )


def get_system_prompt() -> str:
    """
    Get the OpenClaw system prompt for LLM-based routing.
    Designed to minimize tokens while maintaining accuracy.
    """
    return """You are OpenClaw, an orchestration conductor.
Your job is to analyze requests and produce routing decisions.
DO NOT execute work - only decide where to route it.

Available intents and their targets:
- PR_FIX → Symphony (PR lifecycle management)
- CODE_CHANGE → DevClaw (code implementation)
- FILE_TASK → DevClaw (file operations)
- DB_READ → MCP_DB (database queries)
- DB_UPDATE → MCP_DB (database mutations)
- NOTIFY → n8n (notifications)
- CMS_EDIT → MCP_CMS (content management)

Output format: JSON ActionPlan with fields:
- route_to: target system
- intent: action type
- payload: task details
- correlation_id: trace ID
- idempotency_key: dedup key

Be concise. Only output valid JSON."""
