# Data Models and Schemas

## Overview

This document describes the data models and JSON schemas used throughout the OpenClaw Orchestration Stack.

## Core Models

### ActionPlan

The primary output of the OpenClaw Conductor's decision engine.

```javascript
{
  "plan_id": "string",           // Unique identifier (plan_*)
  "correlation_id": "string",    // Groups related operations
  "request_id": "string",        // Original request identifier
  
  "intent": {
    "category": "feature_request|bug_report|code_improvement|review|deployment|question|unknown",
    "confidence": 0.95,           // 0.0 to 1.0
    "confidence_level": "high|medium|low",
    "keywords": ["string"]
  },
  
  "routing": {
    "worker_type": "DEVCLAW|SYMPHONY",
    "action_type": "code_generation|code_review|refactoring|bug_fix|test_generation|deployment|documentation|analysis|human_review",
    "confidence": 0.92,           // 0.0 to 1.0
    "reasoning": "string",        // Human-readable routing explanation
    "requires_review": true,      // Whether human review is required
    "estimated_effort": "small|medium|large",
    "priority": 7                 // 1-10, higher = more urgent
  },
  
  "workflow": {
    "steps": [
      {
        "step_number": 1,
        "description": "string",
        "action_type": "code_generation",
        "worker_type": "DEVCLAW",
        "estimated_duration": "5m",
        "dependencies": []
      }
    ],
    "parallel_groups": [[1, 2], [3]]
  },
  
  "requirements": {
    "skills": ["python", "fastapi"],
    "context_files": ["api/routes.py"],
    "dependencies": ["auth_middleware"],
    "constraints": {}
  },
  
  "context": {},                  // Additional context
  "created_at": "2024-01-15T10:30:00Z",
  "expires_at": "2024-01-15T11:30:00Z",
  "version": "1.0",
  "created_by": "openclaw"
}
```

### Task

Represents a unit of work in the system.

```javascript
{
  "task_id": "string",           // Unique identifier (task_*)
  "correlation_id": "string",
  "status": "queued|executing|review_queued|approved|merged|failed|blocked|review_failed|remediation_queued",
  
  "assigned_to": "DEVCLAW|SYMPHONY",
  "claimed_by": "worker-001",     // Worker instance ID
  "claimed_at": "2024-01-15T10:30:00Z",
  "lease_expires_at": "2024-01-15T10:35:00Z",
  
  "retry_count": 0,
  "remediation_count": 0,
  "max_retries": 3,
  
  "payload": {
    // Task-specific data from ActionPlan
    "plan_id": "plan_abc123",
    "intent": {},
    "routing": {}
  },
  
  "result": {
    // Execution result (populated on completion)
    "success": true,
    "output": {},
    "error_message": "string"
  },
  
  "created_at": "2024-01-15T10:25:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:32:00Z"
}
```

### Review

Code review result.

```javascript
{
  "review_id": "string",         // Unique identifier (review_*)
  "task_id": "string",           // Associated task
  
  "result": "approve|reject|blocked",
  "summary": "string",            // Human-readable summary
  
  "findings": {
    "issues": [
      {
        "severity": "critical|high|medium|low|info",
        "file": "string",
        "line": 42,
        "message": "string",
        "suggestion": "string"
      }
    ],
    "suggestions": ["string"],
    "metrics": {
      "complexity": "low|medium|high",
      "test_coverage": "95%",
      "lines_changed": 50
    }
  },
  
  "reviewer_id": "symphony-agent",
  "reviewer_type": "automated|human",
  
  "pr_number": 123,
  "repository": "org/repo",
  
  "duration_seconds": 175,
  "created_at": "2024-01-15T10:32:05Z",
  "completed_at": "2024-01-15T10:35:00Z"
}
```

### AuditEvent

Immutable audit trail entry.

```javascript
{
  "event_id": "string",          // Unique identifier (audit_*)
  "correlation_id": "string",
  
  "timestamp": "2024-01-15T10:30:00Z",
  "actor": "string",              // Who performed the action
  "action": "string",             // Action performed
  
  "payload": {},                  // Event-specific data
  
  "source_ip": "10.0.0.1",
  "user_agent": "string"
}
```

### ExecutionResult

Result of task execution.

```json
{
  "success": true,
  "files_changed": ["auth.py", "test_auth.py"],
  "no_changes": false,
  
  "test_results": {
    "success": true,
    "returncode": 0,
    "stdout": "string",
    "stderr": "string",
    "passed": 15,
    "failed": 0,
    "skipped": 0,
    "duration_seconds": 45
  },
  
  "lint_results": {
    "success": true,
    "violations": []
  },
  
  "security_scan": {
    "success": true,
    "vulnerabilities": []
  },
  
  "pr_url": "https://github.com/org/repo/pull/123",
  "commit_sha": "abc123def456",
  
  "error_message": "string",
  "error_type": "string",
  
  "metadata": {
    "intent": "string",
    "worker_id": "string",
    "duration_seconds": 120
  }
}
```

## Request/Response Models

### IngestRequest

```javascript
{
  "request_id": "string",        // Optional client-provided ID
  "correlation_id": "string",    // Optional groups related requests
  
  "payload": {
    "type": "string",
    "description": "string",
    // Additional fields depending on type
  },
  
  "context": {
    "source": "chat|github_pr|github_issue|cron|api",
    "repository": "string",
    "user": "string"
  },
  
  "priority": 5                   // 1-10, default: 5
}
```

### IngestResponse

```json
{
  "success": true,
  "plan_id": "string",
  "correlation_id": "string",
  "request_id": "string",
  
  "intent": {
    "category": "string",
    "confidence": 0.95,
    "confidence_level": "high|medium|low",
    "keywords": ["string"]
  },
  
  "routing": {
    "worker_type": "DEVCLAW|SYMPHONY",
    "action_type": "string",
    "confidence": 0.92,
    "reasoning": "string",
    "requires_review": true,
    "priority": 7
  },
  
  "message": "string",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### WebhookPayload

```javascript
{
  "event": "task.created|task.completed|task.failed|review.approved|...",
  "timestamp": "2024-01-15T10:30:00Z",
  "webhook_id": "string",
  
  "data": {
    // Event-specific data (see webhooks.md)
  }
}
```

## Enums

### TaskStatus

```python
class TaskStatus(str, Enum):
    QUEUED = "queued"                          # Waiting to be picked up
    EXECUTING = "executing"                    # Currently being worked on
    REVIEW_QUEUED = "review_queued"           # Awaiting review
    APPROVED = "approved"                      # Review passed
    MERGED = "merged"                          # Successfully merged
    FAILED = "failed"                          # Execution failed
    BLOCKED = "blocked"                        # Blocked pending info
    REVIEW_FAILED = "review_failed"           # Review found issues
    REMEDIATION_QUEUED = "remediation_queued" # Fix queued
```

### WorkerType

```python
class WorkerType(str, Enum):
    DEVCLAW = "DEVCLAW"    # Autonomous coding agent
    SYMPHONY = "SYMPHONY"  # Human-in-the-loop validation
```

### ActionType

```python
class ActionType(str, Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    BUG_FIX = "bug_fix"
    TEST_GENERATION = "test_generation"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    HUMAN_REVIEW = "human_review"
```

### IntentCategory

```python
class IntentCategory(str, Enum):
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    CODE_IMPROVEMENT = "code_improvement"
    QUESTION = "question"
    DEPLOYMENT = "deployment"
    REVIEW = "review"
    UNKNOWN = "unknown"
```

### ReviewResult

```python
class ReviewResult(str, Enum):
    APPROVE = "approve"    # Changes approved
    REJECT = "reject"      # Changes rejected, remediation needed
    BLOCKED = "blocked"    # Blocked pending information
```

### ConfidenceLevel

```python
class ConfidenceLevel(str, Enum):
    HIGH = "high"      # > 0.9
    MEDIUM = "medium"  # 0.7 - 0.9
    LOW = "low"        # < 0.7
```

## Configuration Schemas

### Repository Configuration (.openclaw/review.yaml)

```yaml
repo:
  name: "string"              # Repository name
  language: "python|rust|node|mixed"
  profile_default: "STANDARD|MINIMAL|STRICT"
  description: "string"

commands:
  test:
    - "string"               # Test commands
  lint:
    - "string"               # Lint commands
  format:
    - "string"               # Format commands
  build:
    - "string"               # Build commands

security:
  dependency_scan:
    - "string"
  secret_scan:
    - "string"
  sast:
    - "string"

review:
  auto_merge: false
  require_approval: true
  reviewer_profiles:
    STANDARD:
      check_tests: true
      check_lint: true
      check_security: true
      check_style: true

files:
  include:
    - "glob_pattern"
  exclude:
    - "glob_pattern"

notifications:
  slack:
    webhook_url: "string"
    channel: "string"
  email:
    on_failure: true
    on_success: false
    recipients:
      - "email@example.com"
```

### Global Configuration (config/openclaw.yaml)

```yaml
openclaw:
  routing:
    confidence_threshold: 0.7
    auto_review_threshold: 0.9
    default_worker: "DEVCLAW"
    
    intents:
      feature_request: "DEVCLAW"
      bug_report: "DEVCLAW"
      review: "SYMPHONY"
  
  workers:
    devclaw:
      max_concurrent: 5
      timeout: 300
      retry_attempts: 3
    
    symphony:
      max_concurrent: 3
      timeout: 600
  
  queue:
    type: "sqlite"  # sqlite, redis, rabbitmq
    poll_interval: 5
    batch_size: 10
  
  audit:
    enabled: true
    retention_days: 365
  
  metrics:
    enabled: true
    port: 9090
```

## Validation Rules

### ActionPlan Validation

```python
# plan_id: required, matches pattern ^plan_[a-z0-9]{8,}$
# correlation_id: required
# request_id: required
# intent.confidence: 0.0 to 1.0
# routing.priority: 1 to 10
# created_at: ISO 8601 datetime
```

### Task Validation

```python
# task_id: required, matches pattern ^task_[a-z0-9]{8,}$
# status: must be valid TaskStatus
# assigned_to: must be valid WorkerType
# retry_count: >= 0
# created_at: ISO 8601 datetime
```

### Review Validation

```python
# review_id: required
# task_id: required, must reference existing task
# result: must be valid ReviewResult
# findings.issues[*].severity: critical|high|medium|low|info
# created_at: ISO 8601 datetime
```

## JSON Schema (OpenAPI)

Complete OpenAPI schema available at runtime:

```
GET /openapi.json
```

Or view interactive documentation:

```
GET /docs    # Swagger UI
GET /redoc   # ReDoc
```

## TypeScript Definitions

```typescript
// Core types for TypeScript consumers

interface ActionPlan {
  plan_id: string;
  correlation_id: string;
  request_id: string;
  intent: IntentClassification;
  routing: RoutingDecision;
  workflow?: WorkflowDefinition;
  requirements?: TaskRequirements;
  context?: Record<string, unknown>;
  created_at: string;
  expires_at?: string;
  version: string;
}

interface IntentClassification {
  category: IntentCategory;
  confidence: number;
  confidence_level: ConfidenceLevel;
  keywords: string[];
}

interface RoutingDecision {
  worker_type: WorkerType;
  action_type: ActionType;
  confidence: number;
  reasoning: string;
  requires_review: boolean;
  estimated_effort?: string;
  priority: number;
}

type TaskStatus = 
  | 'queued' 
  | 'executing' 
  | 'review_queued' 
  | 'approved' 
  | 'merged' 
  | 'failed' 
  | 'blocked' 
  | 'review_failed' 
  | 'remediation_queued';

type WorkerType = 'DEVCLAW' | 'SYMPHONY';
type ActionType = 'code_generation' | 'code_review' | 'refactoring' | 'bug_fix' | 'test_generation' | 'deployment' | 'documentation' | 'analysis' | 'human_review';
type IntentCategory = 'feature_request' | 'bug_report' | 'code_improvement' | 'question' | 'deployment' | 'review' | 'unknown';
type ConfidenceLevel = 'high' | 'medium' | 'low';
type ReviewResult = 'approve' | 'reject' | 'blocked';
```

## Migration Notes

### Version 1.0 to 1.1

- Added `remediation_count` field to Task
- Added `parallel_groups` to WorkflowDefinition
- Deprecated `estimated_duration` string format, use integer seconds

### Version 1.1 to 1.2

- Added `reviewer_type` to Review
- Added `security_scan` to ExecutionResult
- Changed `findings.issues[*].line` from string to integer
