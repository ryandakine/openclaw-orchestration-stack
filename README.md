# OpenClaw Orchestration Stack

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: In Development](https://img.shields.io/badge/Status-In%20Development-orange.svg)]()

> A local-first orchestration system for mixed-language repositories with mandatory review queues and auditable automation workflows.

## Overview

OpenClaw Orchestration Stack is a unified automation system designed to handle complex development workflows across Rust, Python, and Node/TypeScript codebases. It separates concerns between orchestration, execution, and review to create a token-efficient, auditable, and reliable automation pipeline.

## Architecture

The stack is built around four core components that work together to provide end-to-end automation:

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

### Core Components

#### 🧠 OpenClaw (Conductor / Orchestrator)
The system brain responsible for:
- Receiving and parsing incoming requests from users, GitHub events, or automation triggers
- Generating structured `ActionPlan` documents that define what needs to happen
- Routing work to the appropriate components (DevClaw, Symphony, n8n, MCP tools)
- Making high-level decisions without burning tokens on implementation details

**Location:** [`/openclaw/`](./openclaw/)

#### ⚡ DevClaw (Executor / Worker)
The execution engine that:
- Checks out repositories and creates feature branches
- Implements code changes based on ActionPlan specifications
- Runs tests, linters, and security scans
- Commits and pushes changes to remote repositories
- Reports completion status back to the orchestrator

**Location:** [`/devclaw-runner/`](./devclaw-runner/)

#### 🎼 Symphony (PR Manager + Reviewer)
Dual-role component handling:
- **PR Management:** Creating and updating pull requests, managing labels, tracking merge status
- **Reviewer Agent:** Mandatory code review after DevClaw task completion
- Quality gate enforcement with approve/reject/block decisions
- Remediation task creation for failed reviews

**Location:** [`/symphony-bridge/`](./symphony-bridge/)

#### 🔗 n8n (Queue / Workflow / Audit)
The infrastructure backbone providing:
- Task queue management with atomic claiming and lease-based processing
- Workflow orchestration for complex multi-step processes
- Append-only audit logging for compliance and debugging
- Webhook handling for GitHub and external integrations
- Notification delivery and alerting

**Location:** [`/n8n-workflows/`](./n8n-workflows/)

## Quick Start

> ⚠️ **Note:** This project is currently in active development. Quick start instructions will be provided once the initial release is ready.

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for n8n)
- Python 3.11+ (for OpenClaw and DevClaw)
- Git

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd openclaw-orchestration-stack

# Copy environment template
cp .env.example .env
# Edit .env with your configuration

# Start the stack (coming soon)
# docker-compose up -d
```

### Configuration

1. Configure your repositories in `.openclaw/review.yaml`
2. Set up n8n credentials in the web UI
3. Configure GitHub tokens for Symphony PR management

## Project Structure

```
openclaw-orchestration-stack/
├── openclaw/              # Orchestrator and decision engine
│   ├── config/            # Configuration files
│   ├── prompts/           # LLM system prompts
│   └── src/               # Core orchestration logic
│
├── devclaw-runner/        # Task execution worker
│   ├── src/               # Runner implementation
│   ├── templates/         # Language-specific templates
│   └── workers/           # Worker implementations
│
├── symphony-bridge/       # PR management and review
│   ├── github/            # GitHub API integration
│   ├── review/            # Review agent logic
│   └── src/               # Core bridge functionality
│
├── n8n-workflows/         # n8n automation workflows
│   ├── audit/             # Audit logging workflows
│   ├── credentials/       # n8n credential configs
│   └── workflows/         # Task queue workflows
│
├── shared/                # Shared libraries and utilities
│   ├── models/            # Data models
│   ├── schemas/           # JSON schemas and validation
│   └── utils/             # Common utilities
│
├── docs/                  # Documentation
│   ├── api/               # API documentation
│   ├── architecture/      # Architecture diagrams
│   └── guides/            # User and developer guides
│
├── .env.example           # Environment variable template
├── .gitignore             # Git ignore rules
├── PRD.md                 # Product Requirements Document
└── README.md              # This file
```

## Workflow Overview

1. **Request Received** — OpenClaw receives a request (chat, GitHub webhook, cron, etc.)
2. **Action Plan Generated** — OpenClaw creates a structured `ActionPlan` with routing decisions
3. **Task Queued** — n8n writes an audit event and creates a queue item
4. **Task Executed** — DevClaw Runner claims the lease and implements the changes
5. **PR Created** — Symphony opens or updates a pull request
6. **Review Triggered** — Task completion triggers the mandatory review queue
7. **Quality Gate** — Symphony Reviewer analyzes the diff and posts findings
8. **Resolution** — Pass → PR ready for merge / Fail → Remediation task created

## Universal Mixed-Language Support

The stack supports repositories with multiple languages through per-repo configuration:

```yaml
# .openclaw/review.yaml
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

## Task State Machine

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

## Contributing

Contributions are welcome! Please read our [Contributing Guide](docs/guides/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License.

```
MIT License

Copyright (c) 2025 OpenClaw Orchestration Stack Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

**Status:** 🚧 In Active Development | **Version:** 1.2.1 | **Last Updated:** 2025
