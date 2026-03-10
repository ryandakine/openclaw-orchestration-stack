# Troubleshooting Guide

## Quick Diagnostics

```bash
# Run diagnostics script
python scripts/diagnostics.py

# Or check components individually
curl http://localhost:8000/health          # API
curl http://localhost:5678/healthz         # n8n
python -c "from shared.db import execute; execute('SELECT 1')"  # Database
```

## Common Issues

### Installation Issues

#### Python Version Mismatch

**Symptoms:**
```
SyntaxError: invalid syntax
# or
ModuleNotFoundError: No module named 'typing_extensions'
```

**Solution:**
```bash
# Check Python version (need 3.11+)
python3 --version

# Install Python 3.11
sudo apt install python3.11 python3.11-venv

# Create venv with correct version
python3.11 -m venv venv
source venv/bin/activate
```

#### Missing System Dependencies

**Symptoms:**
```
ERROR: Could not build wheels for ...
# or
error: command 'gcc' failed
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt install -y python3-dev gcc build-essential

# macOS
xcode-select --install

# Verify
pip install --upgrade pip setuptools wheel
```

### Startup Issues

#### Port Already in Use

**Symptoms:**
```
OSError: [Errno 98] Address already in use
```

**Solution:**
```bash
# Find process using port
lsof -i :8000
# or
netstat -tlnp | grep 8000

# Kill process
kill -9 <PID>

# Or use different port
PORT=8001 python -m openclaw.src.api
```

#### Database Connection Failed

**Symptoms:**
```
sqlite3.OperationalError: unable to open database file
# or
sqlite3.OperationalError: database is locked
```

**Solution:**
```bash
# Check directory exists and is writable
mkdir -p data
chmod 755 data

# Check disk space
df -h .

# For locked database, check for stuck processes
ps aux | grep openclaw
killall -9 python  # Careful! Kills all Python processes

# Reset database (WARNING: DATA LOSS)
rm data/openclaw.db*
python shared/migrations/runner.py migrate
```

#### Missing Environment Variables

**Symptoms:**
```
KeyError: 'ANTHROPIC_API_KEY'
# or
openclaw.exceptions.ConfigurationError: Missing required config
```

**Solution:**
```bash
# Copy example environment file
cp .env.example .env

# Edit and add required variables
nano .env

# Verify
source .env
echo $ANTHROPIC_API_KEY
```

### API Issues

#### 401 Unauthorized

**Symptoms:**
```json
{"detail": "Invalid API key"}
```

**Solution:**
```bash
# Check API key is set
echo $OPENCLAW_API_KEY

# Verify in request
curl -H "X-API-Key: $OPENCLAW_API_KEY" http://localhost:8000/health

# Check key format (no quotes in env file)
# Wrong: OPENCLAW_API_KEY="key123"
# Right: OPENCLAW_API_KEY=key123
```

#### 500 Internal Server Error

**Symptoms:**
```json
{"detail": "Internal server error"}
```

**Solution:**
```bash
# Check logs
docker-compose logs -f openclaw

# Or if running directly
tail -f logs/openclaw.log

# Enable debug mode
DEBUG=true python -m openclaw.src.api

# Look for stack traces
python -m openclaw.src.api 2>&1 | tee debug.log
```

#### Rate Limiting

**Symptoms:**
```json
{"detail": "Rate limit exceeded"}
```

**Solution:**
```bash
# Check rate limit headers
curl -i http://localhost:8000/health

# Look for:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1234567890

# Wait for reset or increase limit in config
```

### Worker Issues

#### Tasks Not Being Picked Up

**Symptoms:**
- Tasks stuck in `queued` state
- No worker activity in logs

**Solution:**
```bash
# Check worker is running
ps aux | grep devclaw

# Check database for pending tasks
sqlite3 data/openclaw.db "SELECT * FROM tasks WHERE status='queued'"

# Restart worker
killall -f "devclaw_runner"
python -m devclaw_runner.src.worker

# Check worker logs
tail -f logs/worker.log
```

#### Task Execution Failures

**Symptoms:**
- Tasks moving to `failed` state
- Error messages in logs

**Solution:**
```bash
# Check specific task
sqlite3 data/openclaw.db "SELECT * FROM tasks WHERE status='failed' LIMIT 5"

# Check audit trail
sqlite3 data/openclaw.db "SELECT * FROM audit_events WHERE correlation_id='corr_xxx'"

# Retry failed task
curl -X POST http://localhost:8000/tasks/<task_id>/retry \
  -H "X-API-Key: $OPENCLAW_API_KEY"
```

#### Lease Expiration Issues

**Symptoms:**
- Tasks stuck in `executing` state
- Multiple workers claiming same task

**Solution:**
```bash
# Check for expired leases
sqlite3 data/openclaw.db "SELECT id, claimed_by, lease_expires_at FROM tasks WHERE status='executing' AND lease_expires_at < datetime('now')"

# Reset stuck tasks
sqlite3 data/openclaw.db "UPDATE tasks SET status='queued', claimed_by=NULL, claimed_at=NULL, lease_expires_at=NULL WHERE status='executing' AND lease_expires_at < datetime('now', '-5 minutes')"

# Increase lease duration in .env
LEASE_DURATION=600  # 10 minutes
```

### GitHub Integration Issues

#### Webhook Not Received

**Symptoms:**
- No events in OpenClaw logs
- PRs not triggering actions

**Solution:**
```bash
# Verify webhook is configured
curl -H "Authorization: token $GITHUB_API_KEY" \
  https://api.github.com/repos/<owner>/<repo>/hooks

# Check webhook deliveries (in GitHub UI)
# Settings -> Webhooks -> Recent Deliveries

# Test webhook manually
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{"action": "opened", ...}'
```

#### Invalid Webhook Signature

**Symptoms:**
```
Invalid webhook signature
```

**Solution:**
```bash
# Verify secret matches
echo $GITHUB_WEBHOOK_SECRET

# Check signature calculation
python3 << 'EOF'
import hmac
import hashlib

secret = "your-secret"
payload = b'{"action": "opened"}'
signature = 'sha256=' + hmac.new(
    secret.encode(),
    payload,
    hashlib.sha256
).hexdigest()
print(f"X-Hub-Signature-256: {signature}")
EOF
```

#### GitHub API Rate Limit

**Symptoms:**
```json
{"message": "API rate limit exceeded"}
```

**Solution:**
```bash
# Check rate limit status
curl -H "Authorization: token $GITHUB_API_KEY" \
  https://api.github.com/rate_limit

# Use GitHub App instead of PAT (higher limits)
# Or wait for reset

# Implement caching to reduce API calls
```

#### Authentication Failed

**Symptoms:**
```
Bad credentials
```

**Solution:**
```bash
# Test token
curl -H "Authorization: token $GITHUB_API_KEY" \
  https://api.github.com/user

# Check token permissions (needs repo scope)
curl -H "Authorization: token $GITHUB_API_KEY" \
  https://api.github.com/users/<username>/repos

# Regenerate token if needed
```

### Database Issues

#### Corrupted Database

**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Solution:**
```bash
# Stop all services
docker-compose down

# Backup corrupted database
cp data/openclaw.db data/openclaw.db.corrupted.$(date +%s)

# Try to recover
sqlite3 data/openclaw.db ".recover" | sqlite3 data/openclaw.db.recovered

# If recovery fails, restore from backup
cp backups/openclaw.db.$(date -d '1 day ago' +%Y%m%d) data/openclaw.db

# Or start fresh (DATA LOSS)
rm data/openclaw.db*
python shared/migrations/runner.py migrate
```

#### Slow Queries

**Symptoms:**
- High response times
- Worker timeouts

**Solution:**
```bash
# Check query performance
sqlite3 data/openclaw.db "EXPLAIN QUERY PLAN SELECT * FROM tasks WHERE status='queued'"

# Analyze and optimize
sqlite3 data/openclaw.db "ANALYZE"

# Check indexes
sqlite3 data/openclaw.db ".indexes tasks"

# Vacuum database
sqlite3 data/openclaw.db "VACUUM"
```

#### WAL File Growing

**Symptoms:**
- Large `-wal` and `-shm` files
- Disk space issues

**Solution:**
```bash
# Force WAL checkpoint
sqlite3 data/openclaw.db "PRAGMA wal_checkpoint(TRUNCATE)"

# Configure auto-checkpoint
sqlite3 data/openclaw.db "PRAGMA wal_autocheckpoint=1000"

# Monitor WAL size
ls -lh data/openclaw.db-*
```

### n8n Issues

#### n8n Won't Start

**Symptoms:**
```
Error: Port 5678 is already in use
```

**Solution:**
```bash
# Find and kill existing n8n
pkill -f n8n

# Or use different port
N8N_PORT=5679 n8n
```

#### Workflow Execution Failed

**Symptoms:**
- Workflows show error status
- Tasks not being created

**Solution:**
```bash
# Check n8n logs
n8n 2>&1 | tee n8n.log

# Verify database connection
n8n execute --id workflow_id

# Check webhook URLs are accessible
curl http://localhost:5678/webhook/task-created
```

#### Credential Issues

**Symptoms:**
```
Credentials could not be decrypted
```

**Solution:**
```bash
# Reset n8n encryption key (will lose existing credentials)
rm ~/.n8n/config

# Or set encryption key
export N8N_ENCRYPTION_KEY="your-secure-key"
```

### Performance Issues

#### High Memory Usage

**Symptoms:**
- System running slow
- Out of memory errors

**Solution:**
```bash
# Check memory usage
ps aux --sort=-%mem | head

# Monitor OpenClaw specifically
ps -o pid,ppid,cmd,%mem,%cpu --sort=-%mem -p $(pgrep -f openclaw)

# Set memory limits
ulimit -v 2097152  # 2GB virtual memory limit

# Adjust worker count (reduce if memory constrained)
MAX_WORKERS=3
```

#### High CPU Usage

**Symptoms:**
- CPU at 100%
- Slow response times

**Solution:**
```bash
# Find CPU-intensive processes
top -o %CPU

# Profile Python code
python -m cProfile -o profile.stats -m openclaw.src.api
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"

# Check for infinite loops in worker logs
grep -i "loop\|infinite\|timeout" logs/worker.log
```

#### Queue Backlog

**Symptoms:**
```
SELECT status, COUNT(*) FROM tasks GROUP BY status;
# Shows many queued tasks
```

**Solution:**
```bash
# Scale up workers
MAX_WORKERS=10

# Check worker efficiency
sqlite3 data/openclaw.db "SELECT assigned_to, AVG(julianday(updated_at) - julianday(created_at)) as avg_time FROM tasks WHERE status='merged' GROUP BY assigned_to"

# Add more worker instances
docker-compose up -d --scale worker=5
```

### Security Issues

#### Suspicious Activity

**Symptoms:**
- Unexpected API calls
- Unknown tasks in queue

**Solution:**
```bash
# Check audit logs
sqlite3 data/openclaw.db "SELECT * FROM audit_events WHERE timestamp > datetime('now', '-1 hour') ORDER BY timestamp DESC"

# Review access logs
grep "POST\|DELETE" logs/access.log

# Rotate API keys
# 1. Generate new keys
# 2. Update .env
# 3. Restart services
# 4. Revoke old keys
```

#### Webhook Security Alert

**Symptoms:**
```
Suspicious webhook payload detected
```

**Solution:**
```bash
# Verify webhook signature
echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET"

# Check IP whitelist (GitHub hooks have specific IPs)
curl https://api.github.com/meta | jq '.hooks'

# Review recent webhook deliveries in GitHub UI
```

## Debugging Tools

### Enable Debug Logging

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Run with verbose output
python -m openclaw.src.api 2>&1 | tee debug.log

# Filter for specific components
grep "openclaw.router" debug.log
grep "devclaw.executor" debug.log
```

### Database Inspection

```bash
# Interactive SQLite shell
sqlite3 data/openclaw.db

# Useful queries
.tables
.schema tasks
SELECT * FROM tasks ORDER BY created_at DESC LIMIT 10;
SELECT status, COUNT(*) FROM tasks GROUP BY status;
SELECT * FROM audit_events WHERE correlation_id='corr_xxx';
```

### API Testing

```bash
# Test with curl
curl -v http://localhost:8000/health

# Test with httpie (if installed)
http POST localhost:8000/ingest payload:='{"type":"test"}'

# Test authentication
curl -H "X-API-Key: $OPENCLAW_API_KEY" http://localhost:8000/ingest \
  -d '{"payload": {"test": true}}'
```

### Network Diagnostics

```bash
# Check connectivity
ping github.com
curl -I https://api.github.com

# Check DNS
nslookup github.com
dig github.com

# Trace route
traceroute github.com
```

## Getting Help

### Collect Diagnostics

```bash
# Run diagnostic script
python scripts/diagnostics.py > diagnostics.txt

# Collect logs
tar -czf logs.tar.gz logs/

# Collect config (sanitize secrets!)
cat .env | grep -v "KEY\|SECRET\|PASSWORD" > config-safe.txt

# Database status
sqlite3 data/openclaw.db ".stats" > db-stats.txt
```

### Report an Issue

When reporting issues, include:

1. **Environment:**
   - OS and version
   - Python version (`python --version`)
   - OpenClaw version

2. **Configuration:**
   - Installation method (Docker, pip, source)
   - Relevant environment variables (redact secrets)

3. **Logs:**
   - Error messages
   - Stack traces
   - Recent log entries

4. **Steps to Reproduce:**
   - What you were doing
   - Expected behavior
   - Actual behavior

### Community Support

- GitHub Issues: https://github.com/openclaw-orchestration-stack/issues
- Documentation: https://docs.openclaw.dev
- Discussions: https://github.com/openclaw-orchestration-stack/discussions

## Emergency Procedures

### System Recovery

```bash
# 1. Stop all services
docker-compose down
pkill -f openclaw

# 2. Backup current state
cp -r data data.backup.$(date +%s)

# 3. Check disk space
df -h

# 4. Restart services
docker-compose up -d

# 5. Verify health
curl http://localhost:8000/health
```

### Data Recovery

```bash
# From backup
systemctl stop openclaw
cp /backups/openclaw.db.$(date -d '1 day ago' +%Y%m%d) data/openclaw.db
systemctl start openclaw

# From WAL (if database corrupted)
sqlite3 data/openclaw.db "PRAGMA wal_checkpoint(RESTART)"
```

### Rollback Deployment

```bash
# Docker rollback
docker-compose down
docker-compose pull
docker-compose up -d

# Or specific version
docker-compose up -d openclaw:1.0.0
```
