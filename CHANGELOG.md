# Changelog

All notable changes to the OpenClaw Orchestration Stack will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of OpenClaw Orchestration Stack
- Comprehensive documentation and deployment guides
- Docker and Kubernetes deployment configurations
- Systemd service files

## [1.2.1] - 2025-01-15

### Added
- Task state machine with comprehensive state transitions
- Lease-based task claiming for reliable worker coordination
- Idempotency support for duplicate request handling
- Batch ingest API for processing multiple requests
- Webhook signature verification for GitHub events
- Security scanning integration (dependency and secret scanning)
- Review queue with mandatory quality gates
- Remediation loop for failed reviews
- Audit trail for all system actions
- Dead letter queue for failed tasks

### Changed
- Improved routing confidence calculation
- Enhanced error handling with structured error responses
- Optimized database queries with strategic indexes
- Updated worker polling interval for better resource utilization

### Fixed
- Race condition in task claiming
- Memory leak in long-running workers
- Webhook payload validation for edge cases
- Database connection pool exhaustion

## [1.2.0] - 2024-12-20

### Added
- Symphony bridge for PR lifecycle management
- Automated code review with configurable profiles
- Multi-language support (Python, Rust, Node.js)
- Repository configuration via `.openclaw/review.yaml`
- Support for mixed-language repositories
- Integration with cargo audit, pip-audit, npm audit
- n8n workflow templates for common automation patterns

### Changed
- Refactored conductor routing logic
- Improved ActionPlan schema with workflow definitions
- Enhanced webhook handler with better error recovery

### Fixed
- GitHub API rate limiting issues
- Task timeout handling in workers
- Database migration rollback functionality

## [1.1.0] - 2024-11-15

### Added
- DevClaw runner for task execution
- Git operations (clone, branch, commit, push)
- Code change application (create, modify, delete, replace)
- Test runner with auto-detection for multiple frameworks
- Python support (pytest, unittest)
- Rust support (cargo test)
- Node.js support (Jest, Mocha, Vitest)
- Task executor with rollback capability

### Changed
- Improved API response times with connection pooling
- Enhanced logging with structured JSON format

### Fixed
- SQLite WAL mode configuration
- Task retry logic with exponential backoff
- Worker heartbeat mechanism

## [1.0.0] - 2024-10-01

### Added
- OpenClaw conductor with intent classification
- REST API with FastAPI
- Request ingestion endpoint
- Action plan generation
- Routing decisions (DEVCLAW, SYMPHONY)
- SQLite database with WAL mode
- Connection pooling
- Database migrations system
- Health check endpoint
- Docker support
- Comprehensive test suite

### Security
- API key authentication
- Input validation with Pydantic
- SQL injection prevention
- CORS configuration

## Version History

### Pre-1.0 (Alpha/Beta)

#### [0.9.0] - 2024-09-01
- Beta release with core functionality
- Initial GitHub integration
- Basic webhook handling

#### [0.8.0] - 2024-08-01
- Alpha release
- Proof of concept for routing engine
- Initial database schema

#### [0.1.0] - 2024-06-01
- Project initialization
- Architecture design
- Technology selection

---

## Release Notes Template

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security improvements
```

## Categories

### Added
- New features
- New integrations
- New documentation

### Changed
- Changes to existing functionality
- Performance improvements
- UI/UX updates

### Deprecated
- Features marked for removal
- API endpoints being phased out

### Removed
- Deleted features
- Removed dependencies

### Fixed
- Bug fixes
- Error corrections
- Edge case handling

### Security
- Security patches
- Vulnerability fixes
- Authentication/authorization improvements

---

## Upgrading

### Upgrading to 1.2.x

1. Backup database:
   ```bash
   cp data/openclaw.db data/openclaw.db.backup
   ```

2. Run migrations:
   ```bash
   python shared/migrations/runner.py migrate
   ```

3. Update configuration:
   - Add new required environment variables
   - Review updated configuration options

4. Restart services:
   ```bash
   docker-compose up -d
   ```

### Upgrading to 1.1.x

1. Update Python to 3.11+
2. Install new dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Update n8n to 1.0.0+

### Upgrading to 1.0.x

1. Fresh installation recommended
2. Migrate data manually if needed

---

## Deprecation Notices

### Deprecated in 1.2.0

- `estimated_duration` string format in ActionPlan (use integer seconds)
- Old webhook payload format (migrate to v2)

### Removed in 1.1.0

- Legacy task queue (replaced with lease-based system)
- File-based configuration (use YAML)

---

## Migration Guides

See [docs/guides/migration.md](docs/guides/migration.md) for detailed migration instructions.

---

## Contributing

To add changelog entries:

1. Add entry under `[Unreleased]` section
2. Use appropriate category
3. Include issue/PR reference when applicable
4. Be concise but descriptive

Example:
```markdown
### Added
- Add support for GitLab webhooks (#123)
```
