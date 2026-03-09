# PRD: OpenClaw Orchestration Stack with Symphony PR Management, DevClaw Execution, and Mandatory Reviewer Queue

**Version:** 1.2.1
**Status:** READY-TO-BUILD
**Owner:** You
**Scope:** Local-first orchestration for mixed-language repos (Rust, Python, Node/TypeScript), with OpenClaw as conductor, DevClaw as executor, Symphony as PR/issue manager and reviewer, and n8n/MCP as modular infrastructure.

---

## 1) Executive Summary

This PRD defines a unified orchestration system where:

* **OpenClaw** is the global orchestrator and decision engine
* **DevClaw** performs implementation work
* **Symphony** manages PR lifecycle and can also act as the **Reviewer agent**
* **n8n** handles queues, webhooks, notifications, and append-only audit logging
* **MCP servers** provide scoped, tool-based access to databases and other structured systems

The goal is to build a lean, auditable, token-efficient automation stack where OpenClaw delegates work instead of doing it directly, and where **all completed work must pass through a mandatory review queue** before it is considered done.

---

## 2) Problem Statement

Current AI/agent workflows tend to fail in one or more of these ways:

* the orchestrator burns tokens doing work instead of routing it
* code changes get created without a consistent review process
* repo workflows become inconsistent across languages
* PR state, execution state, and review state drift apart
* auditability is poor: it is hard to trace what happened, when, and why
* retries and crashes create duplicate jobs or orphaned PR states

---

## 3) Product Goals

### 3.1 Primary Goals

1. Make **OpenClaw** the single orchestration brain.
2. Route implementation work to **DevClaw**, not OpenClaw.
3. Route PR lifecycle and review workflow to **Symphony**.
4. Enforce a **mandatory review queue** after every completed DevClaw task.
5. Support mixed-language repos using per-repo config, not hardcoded tool assumptions.
6. Maintain an **append-only audit trail** for all delegated actions.
7. Keep the stack modular, cheap, and locally runnable.
8. Make retries, crashes, and duplicate deliveries safe via idempotency and leasing.

---

## 4) Core Roles and Responsibilities

### 4.1 OpenClaw — Conductor / Orchestrator

OpenClaw is the system brain. It decides what should happen next and routes work to Symphony, DevClaw, n8n, or MCP tools.

### 4.2 DevClaw — Executor / Worker

DevClaw is responsible for checking out repos, making code changes, running checks, committing and pushing code.

### 4.3 Symphony — PR Manager and Reviewer

Symphony manages PR creation/update, issue/PR status, labels, merge-state rules, and acts as the **Reviewer agent** after work is submitted.

### 4.4 n8n — Queue / Workflow / Audit Bus

n8n handles task creation webhooks, queueing tasks, sending notifications, and writing append-only audit events.

### 4.5 MCP Servers — Scoped Tool Access

MCP is used for read-only or tightly-scoped data access with whitelist rules.

---

## 5) System Architecture

```
User / GitHub Event / Automation
            |
            v
      OpenClaw (Conductor)
            |
            | -> one structured action plan
            v
        n8n Router / Workflow Engine
      _______|______________      \
     |         |            |      \-> append-only audit sink
     v         v            v
 DevClaw    Symphony      MCP Tools
 Queue      PR Ops        DB/CMS/etc.
     |
     v
 DevClaw Runner
     |
     v
 Code changes committed/pushed
     |
     v
 task.completed -> n8n
     |
     v
 Review Queue
     |
     v
 Symphony Reviewer Process
     |
     +--> PASS -> PR ready
     +--> FAIL -> remediation task back to DevClaw
```

---

## 6) Primary Workflow

1. OpenClaw receives a request.
2. OpenClaw produces a structured `ActionPlan`.
3. n8n writes an audit event and creates a task queue item.
4. DevClaw Runner claims the task lease and executes the task.
5. DevClaw commits and pushes the result.
6. Symphony opens or updates the PR.
7. DevClaw sends `task.completed`.
8. n8n enqueues a **review task**.
9. Symphony, acting as Reviewer, reviews the PR diff.
10. Symphony posts findings via `task_comment`.
11. Symphony calls `work_finish`.
12. Based on result: approve → PR ready, reject → remediation task, blocked → pending info

---

## 7) Reviewer Agent Specification (Symphony as Reviewer)

When Symphony acts as a reviewer, it must follow this process:

- Read the issue/task context
- Read the PR diff
- Review against the checklist (correctness, bugs, security, style, tests, scope)
- Call `task_comment` with findings
- Then call `work_finish`
- Do **not** run code or tests directly as the reviewer

**Review Outcomes:**
- **Approve**: `work_finish({ role: "reviewer", result: "approve", ... })`
- **Reject**: `work_finish({ role: "reviewer", result: "reject", ... })`
- **Blocked**: `work_finish({ role: "reviewer", result: "blocked", ... })`

---

## 8) Review Queue and Quality Gate Policy

Every completed DevClaw task must be placed into a `review_queue`.
A task is **not complete** when DevClaw finishes execution.
A task is only complete after the reviewer process returns `approve`.

---

## 9) Universal Mixed-Language Review Model

Each repo should define a file: `.openclaw/review.yaml`

Example:
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
    - "cargo clippy -- -D warnings"
    - "ruff check ."
    - "black --check ."
    - "npm run lint"

security:
  dependency_scan:
    - "cargo audit"
    - "pip-audit -r requirements.txt"
    - "npm audit --audit-level=high"
  secret_scan:
    - "gitleaks detect --no-git -v"
```

---

## 10) Reliability, State Management, and Observability

### 10.1 Canonical Task States

```
queued -> executing -> review_queued -> approved -> merged
  |          |            |
  v          v            v
failed    review_failed  blocked
            |
            v
      remediation_queued -> executing
```

### 10.2 Queue Leasing

All queued tasks must support atomic claiming with lease metadata:
```json
{
  "claimed_by": "worker-id",
  "claimed_at": "ISO-8601",
  "lease_expires_at": "ISO-8601"
}
```

### 10.3 Idempotency and Correlation

All contracts must include:
- `correlation_id`
- `idempotency_key`

---

## 11) Phased Implementation Roadmap

### Phase 0 (1–2 weeks): Python-Only Pilot
- Prove end-to-end flow on one real Python repo
- OpenClaw routing, n8n queue + audit log, DevClaw execution, Symphony PR creation and review

### Phase 1: Rust Support + Full Review Queue
- Add Rust repo support and validate mixed command execution
- Queue leasing, dead-letter handling, review remediation loop

### Phase 2: Node/TS + Mixed Monorepo Support
- Support TS/Node repos and mixed monorepos cleanly
- Per-repo config normalization, multi-command review profiles

### Phase 3: Full Observability + Recovery Hardening
- Dashboards, alerts, richer metrics, replay-safe retries

---

## 12) Data Contracts

### 12.1 ActionPlan (OpenClaw Output)
```json
{
  "action_id": "uuid",
  "correlation_id": "uuid",
  "idempotency_key": "string",
  "route_to": "SYMPHONY|DEVCLAW|N8N|MCP_DB|MCP_CMS",
  "intent": "PR_FIX|CODE_CHANGE|FILE_TASK|DB_READ|DB_UPDATE|NOTIFY|CMS_EDIT",
  "payload": {},
  "audit": {
    "requested_by": "user|system",
    "source": "chat|github_pr|github_issue|cron",
    "created_at": "ISO-8601"
  }
}
```

### 12.2 Task (n8n/Internal State Store)
```json
{
  "task_id": "uuid",
  "correlation_id": "uuid",
  "idempotency_key": "string",
  "projectSlug": "string",
  "status": "queued|executing|review_queued|approved|merged|failed|blocked",
  "assigned_to": "DEVCLAW|SYMPHONY",
  "claimed_by": "worker-id",
  "claimed_at": "ISO-8601",
  "lease_expires_at": "ISO-8601",
  "retry_count": 0
}
```

---

## 13) Implementation Checklist

- [ ] OpenClaw system prompt and ActionPlan emitter
- [ ] State store schema (SQLite MVP, Postgres optional)
- [ ] n8n workflows (task.create, task.completed, review.report, audit.append)
- [ ] DevClaw runner
- [ ] Symphony PR bridge
- [ ] audit append sink
- [ ] reviewer queue
- [ ] reviewer process integration with Symphony
- [ ] `.openclaw/review.yaml` support
- [ ] Python template
- [ ] Rust template
- [ ] Node/TS template
- [ ] metrics capture and dashboard

