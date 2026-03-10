# OpenClaw System Design

## Overview

The OpenClaw Orchestration Stack is a **local-first automation system** designed for mixed-language repositories with mandatory review queues and auditable automation workflows. It separates concerns between orchestration, execution, and review to create a token-efficient, auditable, and reliable automation pipeline.

## Architecture Principles

1. **Separation of Concerns** — Each component has a single, well-defined responsibility
2. **Token Efficiency** — The orchestrator routes work without burning tokens on implementation
3. **Mandatory Review Queue** — All completed work must pass through review before being considered done
4. **Auditability** — Every action is logged in an append-only audit trail
5. **Idempotency** — Safe retries and duplicate delivery handling
6. **Local-First** — Runs locally without cloud dependencies

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OpenClaw Orchestration Stack                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   User / GitHub Event / Automation                                      │
│              │                                                          │
│              ▼                                                          │
│        ┌─────────┐                                                      │
│        │OpenClaw │  ◄── Conductor / Orchestrator                        │
│        │(Brain)  │      Decision engine and router                      │
│        └────┬────┘                                                      │
│             │                                                           │
│             ▼                                                           │
│        ┌─────────┐                                                      │
│        │   n8n   │  ◄── Queue / Workflow / Audit Bus                    │
│        │(Router) │      Task queueing, notifications, append-only audit │
│        └────┬────┘                                                      │
│             │                                                           │
│     ┌───────┼───────┐                                                   │
│     ▼       ▼       ▼                                                   │
│  ┌─────┐ ┌─────┐ ┌─────┐                                               │
│  │Dev- │ │Sym- │ │ MCP │                                               │
│  │Claw  │ │phony│ │Tools│                                               │
│  │─────│ │─────│ │─────│                                               │
│  │Exec-│ │PR   │ │Scoped│                                               │
│  │utor │ │Mgmt │ │Access│                                               │
│  └─────┘ └─────┘ └─────┘                                               │
│     │       │                                                           │
│     │       └──────► Review Queue ◄── Mandatory Quality Gate            │
│     │                           │                                       │
│     └───────────────────────────┘                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. OpenClaw (Conductor / Orchestrator) 🧠

**Location:** `/openclaw/`

The system brain responsible for:
- Receiving and parsing incoming requests from users, GitHub events, or automation triggers
- Generating structured `ActionPlan` documents that define what needs to happen
- Routing work to the appropriate components (DevClaw, Symphony, n8n, MCP tools)
- Making high-level decisions without burning tokens on implementation details

**Key Responsibilities:**
- Request intake and validation
- Intent classification
- Routing decision making
- Action plan generation
- Idempotency checking
- Audit event logging

**Design Philosophy:**
- Minimize token usage (don't do work, just route)
- Single responsibility: decision making
- Stateless: all state in database
- Idempotent: same input = same routing decision

### 2. DevClaw (Executor / Worker) ⚡

**Location:** `/devclaw-runner/`

The execution engine that:
- Checks out repositories and creates feature branches
- Implements code changes based on ActionPlan specifications
- Runs tests, linters, and security scans
- Commits and pushes changes to remote repositories
- Reports completion status back to the orchestrator

**Key Responsibilities:**
- Repository checkout and branch management
- Code change application (create, modify, delete, append, replace)
- Test execution across multiple frameworks
- Git operations (commit, push)
- Task result reporting

**Supported Operations:**
- `create` — Create new files
- `modify` — Modify existing files
- `delete` — Delete files
- `append` — Append content to files
- `replace` — Search and replace content

**Supported Test Frameworks:**
- Python: pytest, unittest
- Node.js: Jest, Mocha, Vitest
- Rust: cargo test
- Go: go test
- Java: Maven, Gradle

### 3. Symphony (PR Manager + Reviewer) 🎼

**Location:** `/symphony-bridge/`

Dual-role component handling:
- **PR Management:** Creating and updating pull requests, managing labels, tracking merge status
- **Reviewer Agent:** Mandatory code review after DevClaw task completion
- Quality gate enforcement with approve/reject/block decisions
- Remediation task creation for failed reviews

**Key Responsibilities:**
- GitHub webhook handling
- PR lifecycle management
- Label management
- Automated code review
- Review outcome processing

**Review Process:**
1. Read the issue/task context
2. Read the PR diff
3. Review against checklist (correctness, bugs, security, style, tests, scope)
4. Post findings via `task_comment`
5. Call `work_finish` with result

**Review Outcomes:**
- **Approve** → PR ready for merge
- **Reject** → Remediation task created
- **Blocked** → Pending information

### 4. n8n (Queue / Workflow / Audit Bus) 🔗

**Location:** `/n8n-workflows/`

The infrastructure backbone providing:
- Task queue management with atomic claiming and lease-based processing
- Workflow orchestration for complex multi-step processes
- Append-only audit logging for compliance and debugging
- Webhook handling for GitHub and external integrations
- Notification delivery and alerting

**Key Responsibilities:**
- Task queue management
- Workflow execution
- Audit logging
- Webhook routing
- Notification delivery

**Workflow Types:**
- Task creation workflows
- Task completion workflows
- Review workflows
- Audit append workflows

### 5. MCP Servers (Scoped Tool Access) 🔐

MCP (Model Context Protocol) servers provide scoped, tool-based access to:
- Databases (read-only or tightly-scoped)
- Content Management Systems
- Other structured systems

**Key Features:**
- Whitelist-based access control
- Read-only or limited write access
- Scoped to specific resources

## Data Flow

### Request Lifecycle

```
1. REQUEST RECEIVED
   User / GitHub / Cron / API
            │
            ▼
2. INTENT CLASSIFICATION
   OpenClaw analyzes request
   Determines intent category
   Assigns confidence score
            │
            ▼
3. ROUTING DECISION
   Maps intent to worker type
   DEVCLAW | SYMPHONY | N8N | MCP
            │
            ▼
4. ACTION PLAN GENERATED
   Structured plan created
   Includes correlation_id
   Idempotency key assigned
            │
            ▼
5. TASK QUEUED (n8n)
   Audit event written
   Task added to queue
   Lease metadata assigned
            │
            ▼
6. TASK EXECUTED
   Worker claims lease
   Executes task
   Reports results
            │
            ▼
7. REVIEW QUEUED
   Completion triggers review
   Symphony reviews changes
   Outcome: approve/reject/block
            │
            ▼
8. RESOLUTION
   ┌─────────────┐     ┌─────────────┐
   │   APPROVE   │     │    REJECT   │
   │   → Merge   │     │→ Remediation│
   └─────────────┘     └─────────────┘
```

### Component Interactions

```
┌──────────┐     ActionPlan      ┌──────────┐
│ OpenClaw │ ──────────────────► │   n8n    │
│(Conductor)│                    │ (Queue)  │
└──────────┘                     └────┬─────┘
      ▲                               │
      │                               │ Task Claim
      │                               ▼
      │                          ┌──────────┐
      │                          │ DevClaw  │
      │                          │(Executor)│
      │                          └────┬─────┘
      │                               │
      │                               │ Code Changes
      │                               ▼
      │                          ┌──────────┐
      │                          │  GitHub  │
      │                          │ (Remote) │
      │                          └────┬─────┘
      │                               │
      │                               │ PR Created
      │                               ▼
      │     Review Results       ┌──────────┐
      └──────────────────────────┤ Symphony │
                                 │(Reviewer)│
                                 └──────────┘
```

## Database Architecture

### SQLite with WAL Mode

The stack uses **SQLite** as its primary database with:
- **WAL (Write-Ahead Logging)** mode for improved concurrency
- **Connection pooling** for thread-safe access
- **JSON columns** for flexible schemas

### Schema Overview

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│     tasks       │         │    reviews      │         │  audit_events   │
├─────────────────┤         ├─────────────────┤         ├─────────────────┤
│ PK id           │◄────────┤ FK task_id      │         │ PK id           │
│    correlation_id│        │    result       │         │    correlation_id│
│    status       │         │    summary      │         │    timestamp    │
│    assigned_to  │         │    findings     │         │    actor        │
│    claimed_by   │         │    reviewer_id  │         │    action       │
│    claimed_at   │         │    created_at   │         │    payload      │
│    lease_expires_at       └─────────────────┘         └─────────────────┘
│    retry_count  │
│    payload      │
│    created_at   │
│    updated_at   │
└─────────────────┘
```

### Task States

```
┌─────────┐     ┌───────────┐     ┌─────────────┐     ┌─────────┐     ┌────────┐
│  queued │────►│ executing │────►│ review_queued│────►│ approved │────►│ merged │
└────┬────┘     └─────┬─────┘     └──────┬──────┘     └─────────┘     └────────┘
     │                │                  │
     ▼                ▼                  ▼
┌─────────┐     ┌─────────────┐   ┌─────────┐
│  failed │     │ review_failed│──►│ blocked │
└─────────┘     └──────┬──────┘   └─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ remediation_queued│
              │    ─► executing   │
              └──────────────────┘
```

**States:**
- `queued` — Task waiting to be picked up
- `executing` — Task currently being worked on
- `review_queued` — Awaiting code review
- `approved` — Approved and ready for merge
- `merged` — Successfully merged
- `failed` — Execution failed
- `blocked` — Blocked pending information
- `review_failed` — Review found issues
- `remediation_queued` — Fix queued after failed review

## Configuration System

### Per-Repository Configuration

Each repository can define `.openclaw/review.yaml`:

```yaml
repo:
  language: mixed
  profile_default: STANDARD

commands:
  test:
    - "cargo test"
    - "pytest -q"
    - "npm test"
  lint:
    - "cargo fmt --check"
    - "ruff check ."
    - "npm run lint"

security:
  dependency_scan:
    - "cargo audit"
    - "pip-audit -r requirements.txt"
  secret_scan:
    - "gitleaks detect --no-git -v"
```

### Language Support

- **Python** — pytest, ruff, black, mypy, pip-audit
- **Rust** — cargo test, cargo fmt, cargo clippy, cargo audit
- **Node.js/TypeScript** — npm test, eslint, prettier, npm audit

## Security Architecture

### Authentication
- API key-based authentication for API endpoints
- GitHub token-based authentication for GitHub operations
- Webhook signature validation

### Authorization
- MCP servers provide scoped access
- Repository-level configuration
- Role-based review requirements

### Audit Trail
- Append-only audit events table
- Correlation IDs for tracing
- Immutable event log

## Scalability Considerations

### Current Design (Single Node)
- SQLite database with WAL mode
- In-memory queues
- Single orchestrator instance

### Scaling Path
1. **Read Replicas** — SQLite can be replicated using Litestream
2. **External Queue** — Redis or RabbitMQ for task queue
3. **PostgreSQL** — Drop-in replacement for SQLite
4. **Multi-Instance** — Multiple orchestrator instances with load balancing

## Monitoring and Observability

### Metrics
- Queue depth by status
- Task execution time
- Review turnaround time
- Worker efficiency

### Health Checks
- Database connectivity
- Queue status
- Worker availability
- GitHub API connectivity

### Alerting
- Queue depth thresholds
- Failed task rates
- Review backlog
- System resource usage

## Development Guidelines

### Adding a New Worker Type

1. Define worker type in `openclaw/schemas/action_plan.py`
2. Add routing logic in `openclaw/src/router.py`
3. Create worker implementation
4. Add webhook handlers if needed
5. Update documentation

### Adding a New Task Type

1. Define intent in `openclaw/src/intent.py`
2. Add routing rule
3. Implement executor in appropriate worker
4. Add tests
5. Update schemas

## References

- [Data Flow](./data-flow.md) — Detailed request lifecycle
- [State Machine](./state-machine.md) — Task state transitions
- [API Documentation](../api/rest-api.md) — REST API reference
- [Configuration Guide](../guides/configuration.md) — Configuration options
