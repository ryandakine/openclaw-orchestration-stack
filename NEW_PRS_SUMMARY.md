# New Pull Requests Created

**Date:** 2026-03-09  
**Total PRs:** 5 (3 for executive-brain, 2 for poker-coach)

---

## executive-brain-infrastructure (3 PRs)

### PR 1: API Rate Limiting
**Branch:** `feature/api-rate-limiting`  
**Commit:** `d3349e4`

**Features:**
- Per-endpoint rate limiting:
  - `/chat`: 10 req/min
  - `/state`: 30 req/min
  - `/frameworks`: 60 req/min
  - `/health`: No limit
- Sliding window algorithm
- Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining)
- 429 Too Many Requests responses with Retry-After
- 18 comprehensive tests

**Files Added/Modified:**
- `agent/rate_limiter.py` (new)
- `agent/server.py` (updated)
- `tests/test_rate_limiting.py` (new)
- `requirements.txt` (updated)

---

### PR 2: Request Logging
**Branch:** `feature/request-logging`  
**Commit:** `8aacebd`

**Features:**
- Request logging middleware with structured JSON format
- Logs: timestamp, method, path, client IP, user agent, status, duration
- Log rotation: 100MB max, 7 days retention, gzip compression
- Admin logs endpoint `/logs` with authentication
- Query params: lines, level, format

**Files Added/Modified:**
- `agent/server.py` (updated with middleware)
- `logs/.gitignore` (new)

**Environment Variables:**
- `EXECUTIVE_BRAIN_ADMIN_KEY` - For accessing logs endpoint

---

### PR 3: Graceful Shutdown
**Branch:** `feature/graceful-shutdown`  
**Commit:** `f4783e4`

**Features:**
- SIGTERM/SIGINT signal handling
- Stop accepting new requests (503 during shutdown)
- Wait for in-progress requests (30s timeout)
- Clean database connection closure
- Structured shutdown logging

**Files Modified:**
- `agent/server.py` (lifespan context manager)
- `agent/store.py` (close_store function)

---

## poker-coach (2 PRs)

### PR 4: Metrics Endpoint
**Branch:** `feature/metrics-endpoint`  
**Commit:** `d10d345`
**Status:** ✅ Pushed to origin

**Features:**
- `/metrics` endpoint with JSON metrics:
  - Uptime, memory usage
  - Hands processed count
  - Cache hit/miss ratio
  - Average response time
- Prometheus-compatible format (`?format=prometheus`)
- `/health` endpoint with component status
- Metrics dashboard page (`metrics.html`)
- 29 comprehensive tests

**Files Added/Modified:**
- `dashboard-server.js` (updated)
- `metrics.html` (new)
- `dashboard.html` (updated with link)
- `tests/test_dashboard_server.js` (new)

**PR URL:** https://github.com/ryandakine/poker-coach/pull/new/feature/metrics-endpoint

---

### PR 5: Config Validation
**Branch:** `feature/config-validation`  
**Commit:** `474c8f1`
**Status:** ✅ Pushed to origin

**Features:**
- Comprehensive config validation module
- Validates: env vars, API keys, paths, numeric ranges, URLs, hotkeys
- Detects placeholder values ("your-api-key-here")
- `--validate-config` CLI flag
- Startup validation with fail-fast
- 42 comprehensive tests
- Updated CLAUDE.md documentation

**Files Added/Modified:**
- `config_validator.py` (new - 390 lines)
- `main.py` (updated with validation)
- `tests/test_config_validation.py` (new - 447 lines)
- `CLAUDE.md` (updated with config docs)

**PR URL:** https://github.com/ryandakine/poker-coach/pull/new/feature/config-validation

---

## PR 6: Graceful Shutdown (poker-coach)
**Branch:** `feature/graceful-shutdown`  
**Commit:** `318d288`
**Status:** ✅ Pushed to origin

**Features:**
- SIGTERM/SIGINT handlers
- Active connection tracking
- 503 for new requests during shutdown
- Configurable timeout via `SHUTDOWN_TIMEOUT` env var
- Two-phase shutdown (graceful → forced)
- Structured logging with timestamps

**Files Modified:**
- `dashboard-server.js` (updated)

**PR URL:** https://github.com/ryandakine/poker-coach/pull/new/feature/graceful-shutdown

---

## Summary Table

| # | Project | Branch | Feature | Tests | Status |
|---|---------|--------|---------|-------|--------|
| 1 | executive-brain | `feature/api-rate-limiting` | Rate limiting | 18 | Local |
| 2 | executive-brain | `feature/request-logging` | Request logging | - | Local |
| 3 | executive-brain | `feature/graceful-shutdown` | Graceful shutdown | - | Local |
| 4 | poker-coach | `feature/metrics-endpoint` | Metrics endpoint | 29 | ✅ Pushed |
| 5 | poker-coach | `feature/config-validation` | Config validation | 42 | ✅ Pushed |
| 6 | poker-coach | `feature/graceful-shutdown` | Graceful shutdown | - | ✅ Pushed |

**Note:** executive-brain branches are local only (no remote configured). To push:
```bash
cd /home/ryan/executive-brain-infrastructure
git remote add origin <repo-url>
git push -u origin feature/api-rate-limiting
git push -u origin feature/request-logging
git push -u origin feature/graceful-shutdown
```

---

**All PRs ready for review! 🎉**
