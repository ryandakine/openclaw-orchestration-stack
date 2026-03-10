# n8n Workflows for OpenClaw Orchestration Stack

This directory contains n8n workflow definitions for the OpenClaw Orchestration Stack.

## Overview

These workflows handle the core orchestration functions:
- Task creation and queueing
- Task completion handling
- Review processing and routing
- Audit logging
- Notifications

## Workflows

### 1. task-create.json
**Trigger:** `POST /webhook/task/create`

Creates a new task in the system and initiates the workflow.

**Flow:**
1. Receive webhook with task payload
2. Validate required fields (intent, correlation_id, idempotency_key)
3. Insert task into SQLite database
4. Log audit event
5. Send notification
6. Return task ID

**Required Payload:**
```json
{
  "intent": "PR_FIX|CODE_CHANGE|FILE_TASK|...",
  "correlation_id": "uuid",
  "idempotency_key": "unique-key",
  "payload": {},
  "assigned_to": "DEVCLAW|SYMPHONY",
  "requested_by": "user|system",
  "source": "chat|github_pr|github_issue|cron|api"
}
```

### 2. task-completed.json
**Trigger:** `POST /webhook/task/completed`

Handles task completion and creates a review queue entry.

**Flow:**
1. Receive completion webhook
2. Validate payload (task_id, correlation_id, result)
3. Update task status to 'review_queued'
4. Create review record
5. Send notification
6. Trigger review workflow

**Required Payload:**
```json
{
  "task_id": "task-uuid",
  "correlation_id": "corr-uuid",
  "result": "success|failure|partial"
}
```

### 3. review-report.json
**Trigger:** `POST /webhook/review/report`

Processes review results and routes tasks accordingly.

**Flow:**
1. Receive review report
2. Validate result (approve/reject/blocked)
3. Update review record
4. Route based on result:
   - **Approve**: Mark task as approved
   - **Reject**: Create remediation task
   - **Block**: Mark task as blocked
5. Send notification
6. Log audit event

**Required Payload:**
```json
{
  "review_id": "review-uuid",
  "task_id": "task-uuid",
  "result": "approve|reject|blocked",
  "reviewer_id": "reviewer-id",
  "summary": "Review summary",
  "findings": []
}
```

### 4. audit-append.json
**Trigger:** `POST /webhook/audit/append` (or called internally)

Append-only audit logging for all system events.

**Flow:**
1. Receive audit event
2. Validate actor and action
3. Insert into audit_events table
4. Write backup to filesystem
5. Return confirmation

**Required Payload:**
```json
{
  "correlation_id": "corr-uuid",
  "actor": "openclaw|devclaw|symphony|n8n|system|user",
  "action": "task.created|task.completed|...",
  "payload": {},
  "ip_address": "optional",
  "user_agent": "optional"
}
```

### 5. notification-send.json
**Trigger:** `POST /webhook/notification/send`

Sends notifications via multiple channels.

**Flow:**
1. Receive notification request
2. Split by configured channels
3. Send via each channel:
   - Slack
   - Discord
   - Email
   - Webhook
4. Aggregate results
5. Log audit event

**Required Payload:**
```json
{
  "event": "task_created|review_completed|...",
  "message": "Human-readable message",
  "channels": ["slack", "discord", "email", "webhook"],
  "correlation_id": "corr-uuid"
}
```

## Directory Structure

```
n8n-workflows/
├── workflows/           # n8n workflow JSON files
│   ├── task-create.json
│   ├── task-completed.json
│   ├── review-report.json
│   ├── audit-append.json
│   └── notification-send.json
├── credentials/         # Credential templates
│   └── example.json     # Template for all credentials
├── audit/              # Audit log backup directory
├── tests/              # Validation tests
│   ├── test_workflow_structure.py
│   ├── test_workflow_integration.py
│   ├── test_json_validity.py
│   ├── run_all_tests.sh
│   └── __init__.py
└── README.md           # This file
```

## Setup

### 1. Configure Credentials

Copy the example credentials and fill in your values:

```bash
cd n8n-workflows/credentials
cp example.json credentials.json
# Edit credentials.json with your actual values
```

**Important:** Never commit `credentials.json` to git!

### 2. Required Credentials

| Credential Name | Type | Purpose |
|----------------|------|---------|
| `sqlite-credentials` | sqlite | Database operations |
| `slack-credentials` | slackApi | Slack notifications |
| `discord-credentials` | discordWebhook | Discord notifications |
| `smtp-credentials` | smtp | Email notifications |

### 3. Import to n8n

**Option A: n8n UI**
1. Open n8n UI
2. Go to Workflows
3. Click "Import from File"
4. Select each workflow JSON file

**Option B: n8n CLI**
```bash
n8n import:workflow --input=./n8n-workflows/workflows/
```

**Option C: API**
```bash
curl -X POST http://localhost:5678/api/v1/workflows \
  -H "X-N8N-API-KEY: your-api-key" \
  -H "Content-Type: application/json" \
  -d @n8n-workflows/workflows/task-create.json
```

## Testing

Run all tests:
```bash
bash n8n-workflows/tests/run_all_tests.sh
```

Run individual tests:
```bash
# Structure validation
python3 n8n-workflows/tests/test_workflow_structure.py

# Integration tests
python3 n8n-workflows/tests/test_workflow_integration.py

# JSON validity
python3 n8n-workflows/tests/test_json_validity.py
```

## Webhook URLs

Once imported to n8n, webhooks will be available at:

| Workflow | Webhook Path |
|----------|--------------|
| task-create | `POST /webhook/task/create` |
| task-completed | `POST /webhook/task/completed` |
| review-report | `POST /webhook/review/report` |
| audit-append | `POST /webhook/audit/append` |
| notification-send | `POST /webhook/notification/send` |

**Production URLs:**
```
https://your-n8n-instance.com/webhook/task/create
https://your-n8n-instance.com/webhook/task/completed
https://your-n8n-instance.com/webhook/review/report
https://your-n8n-instance.com/webhook/audit/append
https://your-n8n-instance.com/webhook/notification/send
```

## Error Handling

All workflows include:
- Input validation
- Error response nodes
- Error handlers that log to audit
- Retry logic where appropriate

## Database Schema

Workflows expect the SQLite database schema defined in `shared/schemas/schema.sql`:
- `tasks` table - Task state management
- `reviews` table - Review results
- `audit_events` table - Append-only audit log

## Integration with OpenClaw

These workflows are called by:
- **OpenClaw** - Creates tasks via webhook
- **DevClaw Runner** - Reports completion via webhook
- **Symphony** - Submits review reports via webhook

## License

See project root LICENSE file.
