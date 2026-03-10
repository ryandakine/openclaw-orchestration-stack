"""
ActionPlan Schema for OpenClaw Conductor

Defines the Pydantic models for routing decisions and action plans.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator


class WorkerType(str, Enum):
    """Available worker types in the system."""
    DEVCLAW = "DEVCLAW"
    SYMPHONY = "SYMPHONY"


class TaskStatus(str, Enum):
    """Possible task statuses."""
    QUEUED = "queued"
    EXECUTING = "executing"
    REVIEW_QUEUED = "review_queued"
    APPROVED = "approved"
    MERGED = "merged"
    FAILED = "failed"
    BLOCKED = "blocked"


class ActionType(str, Enum):
    """Types of actions that can be performed."""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    BUG_FIX = "bug_fix"
    TEST_GENERATION = "test_generation"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    HUMAN_REVIEW = "human_review"


class IntentCategory(str, Enum):
    """Intent categories for request classification."""
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    CODE_IMPROVEMENT = "code_improvement"
    QUESTION = "question"
    DEPLOYMENT = "deployment"
    REVIEW = "review"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Confidence levels for routing decisions."""
    HIGH = "high"      # > 0.9
    MEDIUM = "medium"  # 0.7 - 0.9
    LOW = "low"        # < 0.7


class IntentClassification(BaseModel):
    """Intent classification result."""
    category: IntentCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: Optional[ConfidenceLevel] = None
    keywords: List[str] = Field(default_factory=list)
    
    @validator("confidence_level", always=True)
    def set_confidence_level(cls, v, values):
        confidence = values.get("confidence", 0.0)
        if confidence > 0.9:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.7:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


class RoutingDecision(BaseModel):
    """Routing decision made by the decision engine."""
    worker_type: WorkerType
    action_type: ActionType
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    requires_review: bool = False
    estimated_effort: Optional[str] = None  # e.g., "small", "medium", "large"
    priority: int = Field(default=5, ge=1, le=10)


class TaskRequirement(BaseModel):
    """Requirements for task execution."""
    skills: List[str] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)


class ExecutionStep(BaseModel):
    """Single step in the execution plan."""
    step_number: int
    description: str
    action_type: ActionType
    worker_type: WorkerType
    estimated_duration: Optional[str] = None
    dependencies: List[int] = Field(default_factory=list)  # Step numbers this depends on


class WorkflowDefinition(BaseModel):
    """Workflow definition for multi-step tasks."""
    steps: List[ExecutionStep]
    parallel_groups: List[List[int]] = Field(default_factory=list)  # Steps that can run in parallel


class ActionPlan(BaseModel):
    """
    Complete action plan for a request.
    
    This is the primary output of the OpenClaw Conductor's decision engine.
    """
    # Identification
    plan_id: str = Field(..., description="Unique identifier for this action plan")
    correlation_id: str = Field(..., description="Groups related operations")
    request_id: str = Field(..., description="Original request identifier")
    
    # Classification
    intent: IntentClassification
    
    # Routing Decision
    routing: RoutingDecision
    
    # Execution Plan
    workflow: Optional[WorkflowDefinition] = None
    
    # Task Requirements
    requirements: TaskRequirement = Field(default_factory=TaskRequirement)
    
    # Context
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for execution"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    version: str = "1.0"
    
    # Audit
    created_by: str = "openclaw"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "plan_id": "plan_001",
                "correlation_id": "corr_001",
                "request_id": "req_001",
                "intent": {
                    "category": "feature_request",
                    "confidence": 0.95,
                    "confidence_level": "high",
                    "keywords": ["add", "feature", "api"]
                },
                "routing": {
                    "worker_type": "DEVCLAW",
                    "action_type": "code_generation",
                    "confidence": 0.92,
                    "reasoning": "Request is clearly a feature development task",
                    "requires_review": True,
                    "priority": 7
                },
                "requirements": {
                    "skills": ["python", "fastapi"],
                    "context_files": ["api/routes.py"],
                    "dependencies": ["auth_middleware"]
                },
                "version": "1.0"
            }
        }


class ActionPlanResult(BaseModel):
    """Result of executing an action plan."""
    plan_id: str
    correlation_id: str
    status: TaskStatus
    output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None


class BatchActionPlan(BaseModel):
    """Multiple action plans for batch processing."""
    batch_id: str
    plans: List[ActionPlan]
    execution_mode: str = "sequential"  # sequential, parallel, or dag
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RoutingConfig(BaseModel):
    """Configuration for routing decisions."""
    default_worker: WorkerType = WorkerType.DEVCLAW
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    auto_review_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=0)
    
    # Routing rules
    intent_routing: Dict[IntentCategory, WorkerType] = Field(
        default_factory=lambda: {
            IntentCategory.FEATURE_REQUEST: WorkerType.DEVCLAW,
            IntentCategory.BUG_REPORT: WorkerType.DEVCLAW,
            IntentCategory.CODE_IMPROVEMENT: WorkerType.DEVCLAW,
            IntentCategory.REVIEW: WorkerType.SYMPHONY,
            IntentCategory.DEPLOYMENT: WorkerType.SYMPHONY,
            IntentCategory.QUESTION: WorkerType.DEVCLAW,
            IntentCategory.UNKNOWN: WorkerType.DEVCLAW,
        }
    )
    
    # Action type routing overrides
    action_routing: Dict[ActionType, WorkerType] = Field(
        default_factory=lambda: {
            ActionType.HUMAN_REVIEW: WorkerType.SYMPHONY,
            ActionType.DEPLOYMENT: WorkerType.SYMPHONY,
        }
    )


# Helper functions

def create_action_plan(
    request_id: str,
    correlation_id: str,
    intent_category: IntentCategory,
    worker_type: WorkerType,
    action_type: ActionType,
    confidence: float = 0.8,
    **kwargs
) -> ActionPlan:
    """
    Helper function to create a basic ActionPlan.
    
    Args:
        request_id: The original request identifier
        correlation_id: For grouping related operations
        intent_category: Classified intent
        worker_type: Target worker
        action_type: Type of action to perform
        confidence: Confidence in the routing decision
        **kwargs: Additional fields for the ActionPlan
    
    Returns:
        ActionPlan instance
    """
    import uuid
    
    plan_id = kwargs.get("plan_id", f"plan_{uuid.uuid4().hex[:8]}")
    
    intent = IntentClassification(
        category=intent_category,
        confidence=confidence,
        keywords=kwargs.get("keywords", [])
    )
    
    routing = RoutingDecision(
        worker_type=worker_type,
        action_type=action_type,
        confidence=confidence,
        reasoning=kwargs.get("reasoning", f"Routed to {worker_type.value} based on intent {intent_category.value}"),
        requires_review=kwargs.get("requires_review", confidence < 0.9),
        priority=kwargs.get("priority", 5)
    )
    
    requirements = TaskRequirement(
        skills=kwargs.get("skills", []),
        context_files=kwargs.get("context_files", []),
        dependencies=kwargs.get("dependencies", []),
        constraints=kwargs.get("constraints", {})
    )
    
    return ActionPlan(
        plan_id=plan_id,
        correlation_id=correlation_id,
        request_id=request_id,
        intent=intent,
        routing=routing,
        requirements=requirements,
        context=kwargs.get("context", {}),
        created_by=kwargs.get("created_by", "openclaw")
    )


def should_require_review(plan: ActionPlan, config: RoutingConfig) -> bool:
    """
    Determine if a plan should require human review based on configuration.
    
    Args:
        plan: The action plan to evaluate
        config: Routing configuration
    
    Returns:
        True if review is required
    """
    # High confidence plans may skip review
    if plan.routing.confidence >= config.auto_review_threshold:
        return False
    
    # SYMPHONY tasks always need review
    if plan.routing.worker_type == WorkerType.SYMPHONY:
        return True
    
    # Deployment tasks always need review
    if plan.routing.action_type == ActionType.DEPLOYMENT:
        return True
    
    # Default based on configuration
    return plan.routing.confidence < config.confidence_threshold
