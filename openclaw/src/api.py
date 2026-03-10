"""
OpenClaw Request Intake API

FastAPI endpoints for ingesting requests and returning action plans.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .intent import classify_intent, IntentCategory
from .router import route_to, RoutingError
from .emitter import emit_action_plan
from .audit import log_audit_event
from .idempotency import check_idempotency, store_idempotency_key
from ..schemas.action_plan import ActionPlan, RoutingDecision, IntentClassification


# API Models

class IngestRequest(BaseModel):
    """Request model for the /ingest endpoint."""
    request_id: Optional[str] = Field(
        default=None,
        description="Client-provided request identifier (optional)"
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Groups related requests (optional)"
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Request payload containing the actual request data"
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context for routing decisions"
    )
    priority: Optional[int] = Field(
        default=5,
        ge=1,
        le=10,
        description="Request priority (1-10, higher = more urgent)"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "payload": {
                    "type": "feature_request",
                    "description": "Add user authentication API endpoint",
                    "language": "python",
                    "framework": "fastapi"
                },
                "context": {
                    "source": "github_webhook",
                    "repository": "myorg/myrepo"
                },
                "priority": 7
            }
        }


class IngestResponse(BaseModel):
    """Response model for the /ingest endpoint."""
    success: bool
    plan_id: str
    correlation_id: str
    request_id: str
    intent: IntentClassification
    routing: RoutingDecision
    message: str
    timestamp: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "plan_id": "plan_a1b2c3d4",
                "correlation_id": "corr_12345678",
                "request_id": "req_87654321",
                "intent": {
                    "category": "feature_request",
                    "confidence": 0.95,
                    "confidence_level": "high",
                    "keywords": ["add", "api", "authentication"]
                },
                "routing": {
                    "worker_type": "DEVCLAW",
                    "action_type": "code_generation",
                    "confidence": 0.92,
                    "reasoning": "Clear feature development request",
                    "requires_review": True,
                    "priority": 7
                },
                "message": "Request ingested successfully",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: datetime
    components: Dict[str, str]


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# FastAPI Application

app = FastAPI(
    title="OpenClaw Conductor API",
    description="Intelligent request routing and orchestration for the OpenClaw stack",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependencies

async def verify_api_key(x_api_key: str = Header(...)):
    """Verify API key for protected endpoints."""
    expected_key = os.environ.get("OPENCLAW_API_KEY")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def generate_correlation_id(request_id: Optional[str] = None) -> str:
    """Generate a correlation ID, optionally based on request ID."""
    if request_id:
        # Use hash of request_id to create consistent correlation
        import hashlib
        hash_val = hashlib.md5(request_id.encode()).hexdigest()[:8]
        return f"corr_{hash_val}"
    return f"corr_{uuid.uuid4().hex[:8]}"


# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow(),
        components={
            "api": "healthy",
            "router": "healthy",
            "intent_classifier": "healthy"
        }
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest_request(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None),
    x_request_id: Optional[str] = Header(None)
) -> IngestResponse:
    """
    Ingest a new request and return an action plan.
    
    This endpoint:
    1. Classifies the intent of the request
    2. Makes a routing decision
    3. Generates an action plan
    4. Emits the plan for execution
    5. Returns the plan details
    
    The idempotency-key header can be used to prevent duplicate processing.
    """
    # Generate or use provided identifiers
    request_id = request.request_id or x_request_id or f"req_{uuid.uuid4().hex[:8]}"
    correlation_id = request.correlation_id or generate_correlation_id(request_id)
    
    # Check idempotency
    if idempotency_key:
        existing_plan = check_idempotency(idempotency_key)
        if existing_plan:
            log_audit_event(
                correlation_id=correlation_id,
                actor="openclaw",
                action="request_deduplicated",
                payload={"idempotency_key": idempotency_key, "request_id": request_id}
            )
            # Return cached response
            return IngestResponse(
                success=True,
                plan_id=existing_plan["plan_id"],
                correlation_id=correlation_id,
                request_id=request_id,
                intent=IntentClassification(**existing_plan["intent"]),
                routing=RoutingDecision(**existing_plan["routing"]),
                message="Request already processed (idempotent)",
                timestamp=datetime.utcnow()
            )
    
    try:
        # Log request received
        background_tasks.add_task(
            log_audit_event,
            correlation_id=correlation_id,
            actor="openclaw",
            action="request_received",
            payload={
                "request_id": request_id,
                "payload_type": request.payload.get("type", "unknown"),
                "priority": request.priority
            }
        )
        
        # Classify intent
        intent = classify_intent(request.payload)
        
        # Make routing decision
        routing = route_to(intent, request.payload, request.context)
        
        # Override priority if specified
        if request.priority:
            routing.priority = request.priority
        
        # Generate action plan
        plan = ActionPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            correlation_id=correlation_id,
            request_id=request_id,
            intent=intent,
            routing=routing,
            context=request.context or {}
        )
        
        # Store idempotency key if provided
        if idempotency_key:
            store_idempotency_key(idempotency_key, plan.dict())
        
        # Emit action plan for execution
        background_tasks.add_task(emit_action_plan, plan)
        
        # Log plan created
        background_tasks.add_task(
            log_audit_event,
            correlation_id=correlation_id,
            actor="openclaw",
            action="action_plan_created",
            payload={
                "plan_id": plan.plan_id,
                "worker_type": routing.worker_type.value,
                "action_type": routing.action_type.value,
                "confidence": routing.confidence
            }
        )
        
        return IngestResponse(
            success=True,
            plan_id=plan.plan_id,
            correlation_id=correlation_id,
            request_id=request_id,
            intent=intent,
            routing=routing,
            message="Request ingested successfully",
            timestamp=datetime.utcnow()
        )
        
    except RoutingError as e:
        log_audit_event(
            correlation_id=correlation_id,
            actor="openclaw",
            action="routing_failed",
            payload={"error": str(e), "request_id": request_id}
        )
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="Routing failed",
                detail=str(e),
                request_id=request_id
            ).dict()
        )
    except Exception as e:
        log_audit_event(
            correlation_id=correlation_id,
            actor="openclaw",
            action="ingest_failed",
            payload={"error": str(e), "request_id": request_id}
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Internal error",
                detail=str(e),
                request_id=request_id
            ).dict()
        )


@app.post("/ingest/batch")
async def ingest_batch(
    requests: List[IngestRequest],
    background_tasks: BackgroundTasks
) -> List[IngestResponse]:
    """
    Ingest multiple requests in a batch.
    
    Each request is processed independently and returns its own action plan.
    """
    responses = []
    for request in requests:
        response = await ingest_request(request, background_tasks)
        responses.append(response)
    return responses


@app.get("/intents")
async def list_intent_categories():
    """List available intent categories."""
    return {
        "categories": [
            {"name": cat.value, "description": get_intent_description(cat)}
            for cat in IntentCategory
        ]
    }


def get_intent_description(category: IntentCategory) -> str:
    """Get human-readable description for intent category."""
    descriptions = {
        IntentCategory.FEATURE_REQUEST: "New functionality or feature requests",
        IntentCategory.BUG_REPORT: "Bug reports and issue fixes",
        IntentCategory.CODE_IMPROVEMENT: "Code refactoring and optimization",
        IntentCategory.REVIEW: "Code review requests",
        IntentCategory.DEPLOYMENT: "Deployment and release requests",
        IntentCategory.QUESTION: "Questions and information requests",
        IntentCategory.UNKNOWN: "Unclear or ambiguous requests"
    }
    return descriptions.get(category, "Unknown category")


@app.get("/workers")
async def list_workers():
    """List available workers and their capabilities."""
    return {
        "workers": [
            {
                "name": "DEVCLAW",
                "description": "Autonomous coding agent",
                "capabilities": [
                    "code_generation",
                    "refactoring",
                    "bug_fix",
                    "test_generation",
                    "documentation"
                ]
            },
            {
                "name": "SYMPHONY",
                "description": "Human-in-the-loop validation",
                "capabilities": [
                    "code_review",
                    "deployment_approval",
                    "security_review",
                    "human_oversight"
                ]
            }
        ]
    }


# Error handlers

@app.exception_handler(RoutingError)
async def routing_error_handler(request, exc):
    """Handle routing errors."""
    return HTTPException(
        status_code=400,
        detail=ErrorResponse(
            error="Routing error",
            detail=str(exc)
        ).dict()
    )


# Application startup/shutdown

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    # Initialize idempotency store
    from .idempotency import init_idempotency_store
    init_idempotency_store()
    
    print("🚀 OpenClaw Conductor API started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("👋 OpenClaw Conductor API shutting down")


# For running directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
