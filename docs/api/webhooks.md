# Webhook Documentation

## Overview

OpenClaw sends webhook events to notify your application of events in real-time. You can register webhooks via the API to receive notifications for task events, review outcomes, and system alerts.

## Webhook Configuration

### Registering a Webhook

```http
POST /webhooks
Content-Type: application/json
X-API-Key: your-api-key
```

```json
{
  "url": "https://myapp.com/webhooks/openclaw",
  "events": ["task.completed", "task.failed"],
  "secret": "whsec_your_signing_secret"
}
```

### Available Events

| Event | Description |
|-------|-------------|
| `task.created` | Task created in queue |
| `task.claimed` | Task claimed by worker |
| `task.completed` | Task execution completed |
| `task.failed` | Task execution failed |
| `task.cancelled` | Task cancelled |
| `review.started` | Review process started |
| `review.completed` | Review completed |
| `review.approved` | Changes approved |
| `review.rejected` | Changes rejected |

## Webhook Payload Structure

All webhook payloads follow this structure:

```javascript
{
  "event": "task.completed",
  "timestamp": "2024-01-15T10:30:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    // Event-specific data
  }
}
```

## Event Payloads

### task.created

Sent when a new task is created.

```json
{
  "event": "task.created",
  "timestamp": "2024-01-15T10:30:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "status": "queued",
    "assigned_to": "DEVCLAW",
    "plan_id": "plan_def456",
    "intent": {
      "category": "feature_request",
      "confidence": 0.95
    },
    "routing": {
      "worker_type": "DEVCLAW",
      "action_type": "code_generation"
    },
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

### task.claimed

Sent when a worker claims a task.

```json
{
  "event": "task.claimed",
  "timestamp": "2024-01-15T10:30:05Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "worker_id": "worker-001",
    "claimed_at": "2024-01-15T10:30:05Z",
    "lease_expires_at": "2024-01-15T10:35:05Z"
  }
}
```

### task.completed

Sent when task execution completes successfully.

```json
{
  "event": "task.completed",
  "timestamp": "2024-01-15T10:32:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "previous_status": "executing",
    "new_status": "review_queued",
    "worker_id": "worker-001",
    "duration_seconds": 115,
    "result": {
      "success": true,
      "files_changed": ["auth.py", "test_auth.py"],
      "test_results": {
        "success": true,
        "passed": 15,
        "failed": 0
      },
      "pr_url": "https://github.com/org/repo/pull/123"
    },
    "completed_at": "2024-01-15T10:32:00Z"
  }
}
```

### task.failed

Sent when task execution fails.

```json
{
  "event": "task.failed",
  "timestamp": "2024-01-15T10:31:30Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "previous_status": "executing",
    "new_status": "failed",
    "worker_id": "worker-001",
    "duration_seconds": 85,
    "error": {
      "type": "TestFailureError",
      "message": "Tests failed: test_auth.py::test_login",
      "details": {
        "stdout": "...",
        "stderr": "...",
        "returncode": 1
      }
    },
    "retry_count": 0,
    "max_retries": 3,
    "can_retry": true,
    "failed_at": "2024-01-15T10:31:30Z"
  }
}
```

### task.cancelled

Sent when a task is cancelled.

```json
{
  "event": "task.cancelled",
  "timestamp": "2024-01-15T10:30:30Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "previous_status": "queued",
    "cancelled_by": "user123",
    "reason": "User requested cancellation",
    "cancelled_at": "2024-01-15T10:30:30Z"
  }
}
```

### review.started

Sent when a review process begins.

```json
{
  "event": "review.started",
  "timestamp": "2024-01-15T10:32:05Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "review_id": "review_def789",
    "pr_number": 123,
    "repository": "org/repo",
    "reviewer": "symphony-agent",
    "started_at": "2024-01-15T10:32:05Z"
  }
}
```

### review.completed

Sent when a review is completed.

```json
{
  "event": "review.completed",
  "timestamp": "2024-01-15T10:35:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "review_id": "review_def789",
    "pr_number": 123,
    "repository": "org/repo",
    "reviewer": "symphony-agent",
    "result": "approved",
    "summary": "Code looks good, tests pass",
    "findings": {
      "issues": [],
      "suggestions": [
        "Consider adding type hints to the new function"
      ],
      "metrics": {
        "complexity": "low",
        "test_coverage": "95%"
      }
    },
    "duration_seconds": 175,
    "completed_at": "2024-01-15T10:35:00Z"
  }
}
```

### review.approved

Sent when changes are approved.

```json
{
  "event": "review.approved",
  "timestamp": "2024-01-15T10:35:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "review_id": "review_def789",
    "pr_number": 123,
    "repository": "org/repo",
    "approved_by": "symphony-agent",
    "approved_at": "2024-01-15T10:35:00Z",
    "mergeable": true
  }
}
```

### review.rejected

Sent when changes are rejected.

```json
{
  "event": "review.rejected",
  "timestamp": "2024-01-15T10:35:00Z",
  "webhook_id": "wh_abc123",
  "data": {
    "task_id": "task_abc123",
    "correlation_id": "corr_xyz789",
    "review_id": "review_def789",
    "pr_number": 123,
    "repository": "org/repo",
    "rejected_by": "symphony-agent",
    "reason": "Security issues found",
    "findings": {
      "issues": [
        {
          "severity": "high",
          "file": "auth.py",
          "line": 45,
          "message": "Potential SQL injection vulnerability"
        }
      ]
    },
    "remediation_required": true,
    "rejected_at": "2024-01-15T10:35:00Z"
  }
}
```

## Security

### Signature Verification

Webhooks are signed with HMAC-SHA256. Verify the signature to ensure the webhook came from OpenClaw:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify webhook signature.
    
    Args:
        payload: Raw request body
        signature: X-OpenClaw-Signature header value
        secret: Your webhook signing secret
    
    Returns:
        True if signature is valid
    """
    # Expected format: "sha256=<hex>"
    if not signature.startswith("sha256="):
        return False
    
    expected_sig = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_sig}", signature)

# Usage
@app.route('/webhooks/openclaw', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-OpenClaw-Signature')
    payload = request.get_data()
    
    if not verify_webhook(payload, signature, WEBHOOK_SECRET):
        return 'Invalid signature', 401
    
    # Process webhook
    event = request.json
    process_event(event)
    
    return 'OK', 200
```

### Node.js

```javascript
const crypto = require('crypto');

function verifyWebhook(payload, signature, secret) {
  const expectedSig = crypto
    .createHmac('sha256', secret)
    .update(payload, 'utf8')
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(`sha256=${expectedSig}`)
  );
}

// Express middleware
app.post('/webhooks/openclaw', express.raw({type: 'application/json'}), (req, res) => {
  const signature = req.headers['x-openclaw-signature'];
  
  if (!verifyWebhook(req.body, signature, WEBHOOK_SECRET)) {
    return res.status(401).send('Invalid signature');
  }
  
  const event = JSON.parse(req.body);
  processEvent(event);
  
  res.send('OK');
});
```

## Retry Policy

OpenClaw retries failed webhook deliveries with exponential backoff:

| Attempt | Delay |
|---------|-------|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4 | 8 seconds |
| 5 | 16 seconds |

A delivery is considered successful if your endpoint returns a `2xx` status code.

### Handling Retries

```python
# Use idempotency key to handle retries
@app.route('/webhooks/openclaw', methods=['POST'])
def handle_webhook():
    event = request.json
    event_id = request.headers.get('X-OpenClaw-Event-ID')
    
    # Check if already processed
    if is_processed(event_id):
        return 'Already processed', 200
    
    # Process event
    process_event(event)
    
    # Mark as processed
    mark_processed(event_id)
    
    return 'OK', 200
```

## Best Practices

### 1. Return 200 Quickly

Process webhooks asynchronously:

```python
@app.route('/webhooks/openclaw', methods=['POST'])
def handle_webhook():
    event = request.json
    
    # Queue for async processing
    queue.enqueue(process_event, event)
    
    # Return immediately
    return 'Accepted', 200
```

### 2. Handle Duplicates

Use idempotency keys to handle duplicate deliveries:

```python
def process_event(event):
    event_id = f"{event['webhook_id']}:{event['timestamp']}"
    
    # Try to insert into processed table
    try:
        db.execute(
            "INSERT INTO processed_webhooks (id) VALUES (?)",
            (event_id,)
        )
    except IntegrityError:
        # Already processed
        return
    
    # Process event
    ...
```

### 3. Verify Timestamps

Reject old webhooks to prevent replay attacks:

```python
import time
from datetime import datetime

def verify_timestamp(timestamp_str, max_age=300):
    event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    event_timestamp = event_time.timestamp()
    now = time.time()
    
    return abs(now - event_timestamp) < max_age
```

### 4. Log Everything

```python
import logging

logger = logging.getLogger('webhooks')

@app.route('/webhooks/openclaw', methods=['POST'])
def handle_webhook():
    event = request.json
    
    logger.info(f"Received webhook: {event['event']}", extra={
        'webhook_id': event['webhook_id'],
        'event_type': event['event'],
        'correlation_id': event['data'].get('correlation_id')
    })
    
    try:
        process_event(event)
        logger.info(f"Processed webhook successfully")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Failed to process webhook: {e}")
        raise
```

## Testing Webhooks

### Local Development with ngrok

```bash
# Install ngrok
npm install -g ngrok

# Expose local server
ngrok http 3000

# Register webhook with ngrok URL
curl -X POST http://localhost:8000/webhooks \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "url": "https://abc123.ngrok.io/webhooks/openclaw",
    "events": ["task.completed"],
    "secret": "test-secret"
  }'

# Trigger a test event
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: $API_KEY" \
  -d '{"payload": {"type": "test"}}'
```

### Webhook Testing Endpoint

```http
POST /webhooks/test
Content-Type: application/json
X-API-Key: your-api-key
```

```json
{
  "webhook_id": "wh_abc123",
  "event": "task.completed",
  "url": "https://myapp.com/webhooks/openclaw"
}
```

Sends a test event to your webhook endpoint.

## Troubleshooting

### Webhook Not Received

1. **Check webhook is registered:**
```bash
curl http://localhost:8000/webhooks \
  -H "X-API-Key: $API_KEY"
```

2. **Verify URL is accessible:**
```bash
curl -I https://myapp.com/webhooks/openclaw
```

3. **Check firewall/network:**
```bash
# Ensure port is open
nc -zv myapp.com 443
```

### Signature Verification Failing

1. **Check secret matches:**
```bash
echo $WEBHOOK_SECRET
```

2. **Verify payload is raw bytes:**
```python
# Don't parse JSON before verifying
payload = request.get_data()  # Raw bytes
signature = request.headers.get('X-OpenClaw-Signature')
verify_webhook(payload, signature, secret)
```

3. **Test signature calculation:**
```python
import hmac
import hashlib

secret = "your-secret"
payload = b'{"event": "test"}'
expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
print(f"sha256={expected}")
```

### High Retry Count

If webhooks are being retried frequently:

1. Check endpoint response time (< 5 seconds)
2. Ensure returning 2xx status codes
3. Check server capacity
4. Review error logs

## References

- [REST API](./rest-api.md) — API reference
- [Security Guide](../guides/security.md) — Security best practices
