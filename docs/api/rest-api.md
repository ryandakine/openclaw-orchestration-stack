# REST API Reference

## Base URL

```
Development: http://localhost:8000
Production: https://api.openclaw.example.com
```

## Authentication

All API requests require authentication using an API key header:

```bash
curl -H "X-API-Key: your-api-key" \
  https://api.openclaw.example.com/health
```

## Content Types

- Request: `application/json`
- Response: `application/json`

## Endpoints

### Health Check

Check API health status.

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "api": "healthy",
    "router": "healthy",
    "intent_classifier": "healthy"
  }
}
```

**Status Codes:**
- `200` — Healthy
- `503` — Unhealthy (one or more components down)

---

### Ingest Request

Submit a new request for processing.

```http
POST /ingest
Content-Type: application/json
X-API-Key: your-api-key
Idempotency-Key: unique-key-optional
```

**Request Body:**

```javascript
{
  "request_id": "req_123",           // Optional: client-provided ID
  "correlation_id": "corr_456",      // Optional: groups related requests
  "payload": {
    "type": "feature_request",
    "description": "Add user authentication",
    "language": "python",
    "framework": "fastapi"
  },
  "context": {
    "source": "github_webhook",
    "repository": "myorg/myrepo"
  },
  "priority": 7                      // 1-10, higher = more urgent
}
```

**Response (200 OK):**

```json
{
  "success": true,
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
    "requires_review": true,
    "estimated_effort": "medium",
    "priority": 7
  },
  "message": "Request ingested successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Error Responses:**

```javascript
// 400 Bad Request
{
  "error": "Routing failed",
  "detail": "Unable to determine intent from payload",
  "request_id": "req_87654321",
  "timestamp": "2024-01-15T10:30:00Z"
}

// 401 Unauthorized
{
  "detail": "Invalid API key"
}

// 429 Too Many Requests
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

---

### Batch Ingest

Submit multiple requests in a batch.

```http
POST /ingest/batch
Content-Type: application/json
X-API-Key: your-api-key
```

**Request Body:**

```json
[
  {
    "payload": {"type": "feature_request", "description": "Feature 1"},
    "priority": 5
  },
  {
    "payload": {"type": "bug_report", "description": "Bug 1"},
    "priority": 8
  }
]
```

**Response:**

```json
[
  {
    "success": true,
    "plan_id": "plan_001",
    "correlation_id": "corr_001",
    "request_id": "req_001",
    "intent": {...},
    "routing": {...},
    "message": "Request ingested successfully",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  {
    "success": true,
    "plan_id": "plan_002",
    "correlation_id": "corr_002",
    "request_id": "req_002",
    "intent": {...},
    "routing": {...},
    "message": "Request ingested successfully",
    "timestamp": "2024-01-15T10:30:01Z"
  }
]
```

---

### List Intent Categories

Get available intent classification categories.

```http
GET /intents
```

**Response:**

```json
{
  "categories": [
    {
      "name": "feature_request",
      "description": "New functionality or feature requests"
    },
    {
      "name": "bug_report",
      "description": "Bug reports and issue fixes"
    },
    {
      "name": "code_improvement",
      "description": "Code refactoring and optimization"
    },
    {
      "name": "review",
      "description": "Code review requests"
    },
    {
      "name": "deployment",
      "description": "Deployment and release requests"
    },
    {
      "name": "question",
      "description": "Questions and information requests"
    },
    {
      "name": "unknown",
      "description": "Unclear or ambiguous requests"
    }
  ]
}
```

---

### List Workers

Get available workers and their capabilities.

```http
GET /workers
```

**Response:**

```json
{
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
```

---

### Get Task Status

Get the current status of a task.

```http
GET /tasks/{task_id}
X-API-Key: your-api-key
```

**Response:**

```json
{
  "task_id": "task_abc123",
  "correlation_id": "corr_xyz789",
  "status": "review_queued",
  "assigned_to": "DEVCLAW",
  "claimed_by": "worker-001",
  "claimed_at": "2024-01-15T10:30:00Z",
  "lease_expires_at": "2024-01-15T10:35:00Z",
  "retry_count": 0,
  "payload": {
    "plan_id": "plan_abc123",
    "intent": {...}
  },
  "created_at": "2024-01-15T10:25:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

---

### List Tasks

List tasks with optional filtering.

```http
GET /tasks?status=queued&limit=10&offset=0
X-API-Key: your-api-key
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `assigned_to` | string | Filter by worker type |
| `correlation_id` | string | Filter by correlation ID |
| `limit` | integer | Max results (default: 10, max: 100) |
| `offset` | integer | Pagination offset |

**Response:**

```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "status": "queued",
      "assigned_to": "DEVCLAW",
      "created_at": "2024-01-15T10:25:00Z"
    }
  ],
  "total": 45,
  "limit": 10,
  "offset": 0
}
```

---

### Retry Task

Retry a failed task.

```http
POST /tasks/{task_id}/retry
X-API-Key: your-api-key
```

**Response:**

```json
{
  "task_id": "task_abc123",
  "previous_status": "failed",
  "new_status": "queued",
  "retry_count": 1,
  "message": "Task queued for retry"
}
```

---

### Cancel Task

Cancel a queued or executing task.

```http
POST /tasks/{task_id}/cancel
X-API-Key: your-api-key
```

**Request Body (optional):**

```json
{
  "reason": "User requested cancellation"
}
```

**Response:**

```json
{
  "task_id": "task_abc123",
  "previous_status": "executing",
  "new_status": "cancelled",
  "message": "Task cancelled"
}
```

---

### Get Audit Trail

Get audit events for a correlation ID.

```http
GET /audit/{correlation_id}
X-API-Key: your-api-key
```

**Response:**

```json
{
  "correlation_id": "corr_xyz789",
  "events": [
    {
      "id": "audit_001",
      "timestamp": "2024-01-15T10:25:00Z",
      "actor": "openclaw",
      "action": "request_received",
      "payload": {"request_id": "req_001"}
    },
    {
      "id": "audit_002",
      "timestamp": "2024-01-15T10:25:01Z",
      "actor": "openclaw",
      "action": "action_plan_created",
      "payload": {"plan_id": "plan_001"}
    },
    {
      "id": "audit_003",
      "timestamp": "2024-01-15T10:25:02Z",
      "actor": "n8n",
      "action": "task.created",
      "payload": {"task_id": "task_001"}
    }
  ]
}
```

---

### Webhook Registration

Register a webhook for event notifications.

```http
POST /webhooks
Content-Type: application/json
X-API-Key: your-api-key
```

**Request Body:**

```json
{
  "url": "https://myapp.com/webhooks/openclaw",
  "events": ["task.completed", "task.failed", "review.approved"],
  "secret": "webhook-signing-secret"
}
```

**Response:**

```json
{
  "webhook_id": "wh_abc123",
  "url": "https://myapp.com/webhooks/openclaw",
  "events": ["task.completed", "task.failed", "review.approved"],
  "active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### Delete Webhook

Remove a webhook registration.

```http
DELETE /webhooks/{webhook_id}
X-API-Key: your-api-key
```

**Response:** `204 No Content`

---

## Error Codes

| Code | Description | Retryable |
|------|-------------|-----------|
| `400` | Bad Request — Invalid input | No |
| `401` | Unauthorized — Invalid API key | No |
| `403` | Forbidden — Insufficient permissions | No |
| `404` | Not Found — Resource doesn't exist | No |
| `409` | Conflict — Resource already exists | No |
| `422` | Unprocessable Entity — Validation error | No |
| `429` | Too Many Requests — Rate limit exceeded | Yes |
| `500` | Internal Server Error | Yes |
| `503` | Service Unavailable | Yes |

## Rate Limiting

Rate limits are applied per API key:

- **Standard:** 100 requests/minute
- **Burst:** 150 requests/minute (short periods)

**Rate Limit Headers:**

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705315800
X-RateLimit-Retry-After: 45
```

## Pagination

List endpoints support cursor-based pagination:

```http
GET /tasks?limit=10&offset=0
```

**Response includes:**

```json
{
  "tasks": [...],
  "total": 100,
  "limit": 10,
  "offset": 0,
  "next_offset": 10,
  "has_more": true
}
```

## SDK Examples

### Python

```python
import requests

class OpenClawClient:
    def __init__(self, api_key, base_url="http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def ingest(self, payload, **kwargs):
        response = requests.post(
            f"{self.base_url}/ingest",
            headers=self.headers,
            json={"payload": payload, **kwargs}
        )
        response.raise_for_status()
        return response.json()
    
    def get_task(self, task_id):
        response = requests.get(
            f"{self.base_url}/tasks/{task_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

# Usage
client = OpenClawClient("your-api-key")
result = client.ingest({
    "type": "feature_request",
    "description": "Add user authentication"
})
print(f"Plan ID: {result['plan_id']}")
```

### JavaScript

```javascript
class OpenClawClient {
  constructor(apiKey, baseUrl = 'http://localhost:8000') {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
  }

  async ingest(payload, options = {}) {
    const response = await fetch(`${this.baseUrl}/ingest`, {
      method: 'POST',
      headers: {
        'X-API-Key': this.apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ payload, ...options })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    
    return response.json();
  }

  async getTask(taskId) {
    const response = await fetch(`${this.baseUrl}/tasks/${taskId}`, {
      headers: { 'X-API-Key': this.apiKey }
    });
    return response.json();
  }
}

// Usage
const client = new OpenClawClient('your-api-key');
const result = await client.ingest({
  type: 'feature_request',
  description: 'Add user authentication'
});
console.log(`Plan ID: ${result.plan_id}`);
```

### cURL

```bash
# Set variables
API_KEY="your-api-key"
BASE_URL="http://localhost:8000"

# Health check
curl -H "X-API-Key: $API_KEY" $BASE_URL/health

# Ingest request
curl -X POST $BASE_URL/ingest \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "type": "feature_request",
      "description": "Add user authentication"
    },
    "priority": 7
  }'

# Get task status
curl -H "X-API-Key: $API_KEY" $BASE_URL/tasks/task_abc123

# List tasks
curl -H "X-API-Key: $API_KEY" "$BASE_URL/tasks?status=queued&limit=5"
```

## OpenAPI Specification

Full OpenAPI/Swagger specification available at:

```
http://localhost:8000/openapi.json
```

Interactive documentation:

```
http://localhost:8000/docs    # Swagger UI
http://localhost:8000/redoc   # ReDoc
```
