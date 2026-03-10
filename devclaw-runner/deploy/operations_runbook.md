# OpenClaw Arbitrage Hunter - Operations Runbook

## Overview

This runbook covers operational procedures for the OpenClaw Arbitrage Hunter deployment, including systemd management, debugging, log analysis, and common issues.

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `systemctl status pred-market-arb.timer` | Check timer status |
| `systemctl start pred-market-arb.service` | Run scanner manually |
| `journalctl -u pred-market-arb.service -f` | Follow logs |
| `python deploy/health_check.py` | Run health check |
| `python deploy/backup_script.py` | Run backup |

---

## Service Management

### Checking Service Status

```bash
# Check timer status
systemctl status pred-market-arb.timer

# Check service status
systemctl status pred-market-arb.service

# List all timers
systemctl list-timers --all

# Check if timer is enabled
systemctl is-enabled pred-market-arb.timer
```

### Starting/Stopping Services

```bash
# Start the timer (enables scheduled runs)
sudo systemctl start pred-market-arb.timer

# Stop the timer (disables scheduled runs)
sudo systemctl stop pred-market-arb.timer

# Run the service manually (immediate execution)
sudo systemctl start pred-market-arb.service

# Restart services after config changes
sudo systemctl daemon-reload
sudo systemctl restart pred-market-arb.timer
```

### Enabling/Disabling Services

```bash
# Enable timer to start on boot
sudo systemctl enable pred-market-arb.timer

# Disable timer from starting on boot
sudo systemctl disable pred-market-arb.timer

# Enable both service and timer
sudo systemctl enable pred-market-arb.service pred-market-arb.timer
```

---

## Log Management

### Viewing Logs

```bash
# View all logs for the service
journalctl -u pred-market-arb.service

# Follow logs in real-time
journalctl -u pred-market-arb.service -f

# View logs since last boot
journalctl -u pred-market-arb.service -b

# View logs from the last hour
journalctl -u pred-market-arb.service --since "1 hour ago"

# View logs with specific time range
journalctl -u pred-market-arb.service --since "2024-01-01 00:00:00" --until "2024-01-02 00:00:00"

# View logs with priority filter
journalctl -u pred-market-arb.service -p err

# Show last N lines
journalctl -u pred-market-arb.service -n 100
```

### Log Rotation

Systemd journals are automatically rotated. To check journal disk usage:

```bash
# Check journal size
journalctl --disk-usage

# Vacuum logs older than 30 days
sudo journalctl --vacuum-time=30d

# Vacuum logs to specific size
sudo journalctl --vacuum-size=500M
```

---

## Debugging

### Service Fails to Start

1. **Check service status for errors:**
   ```bash
   systemctl status pred-market-arb.service
   ```

2. **Check journal for detailed errors:**
   ```bash
   journalctl -u pred-market-arb.service --no-pager -n 50
   ```

3. **Verify file permissions:**
   ```bash
   ls -la /home/ryan/openclaw-orchestration-stack/
   ls -la /etc/systemd/system/pred-market-arb.*
   ```

4. **Test configuration:**
   ```bash
   sudo systemd-analyze verify /etc/systemd/system/pred-market-arb.service
   ```

5. **Run manually to see errors:**
   ```bash
   cd /home/ryan/openclaw-orchestration-stack
   PYTHONPATH=/home/ryan/openclaw-orchestration-stack \
   python3 -m devclaw-runner.src.prediction_markets.arb_scanner
   ```

### API Connection Issues

1. **Test API connectivity:**
   ```bash
   python deploy/health_check.py
   ```

2. **Check network connectivity:**
   ```bash
   curl -I https://gamma-api.polymarket.com/markets
   curl -I https://api.elections.kalshi.com/trade-api/v2/markets
   curl -I https://www.predictit.org/api/marketdata/all/
   ```

3. **Verify API keys in .env:**
   ```bash
   cat /home/ryan/openclaw-orchestration-stack/.env | grep -E "(API_KEY|TOKEN)"
   ```

### Database Issues

1. **Check database file permissions:**
   ```bash
   ls -la /home/ryan/openclaw-orchestration-stack/data/*.db
   ```

2. **Verify database integrity:**
   ```bash
   sqlite3 /home/ryan/openclaw-orchestration-stack/data/openclaw.db "PRAGMA integrity_check;"
   ```

3. **Check disk space:**
   ```bash
   df -h /home/ryan/openclaw-orchestration-stack/data
   ```

---

## Health Checks

### Running Health Checks

```bash
# Run full health check
python deploy/health_check.py

# Run health check with JSON output
python deploy/health_check.py --json

# Docker health check
python deploy/health_check.py --docker

# Start health check HTTP server
python deploy/health_check.py --server --port 8080
```

### HTTP Health Endpoint

When running with `--server`, health checks are available at:

- `GET /health` - Full health report
- `GET /ready` - Readiness probe (for Kubernetes)
- `GET /live` - Liveness probe (for Kubernetes)

Example:
```bash
curl http://localhost:8080/health | jq
```

---

## Backup and Recovery

### Running Backups

```bash
# Run full backup
python deploy/backup_script.py

# Backup to specific location
python deploy/backup_script.py --destination /mnt/backups/openclaw

# Backup specific components
python deploy/backup_script.py --type audit
python deploy/backup_script.py --type database
python deploy/backup_script.py --type config

# Upload to S3
python deploy/backup_script.py --s3-bucket my-backup-bucket --s3-prefix openclaw

# Cleanup old backups (keep last 30 days)
python deploy/backup_script.py --cleanup 30
```

### Restoring from Backup

```bash
# List available backups
ls -la /home/ryan/openclaw-orchestration-stack/data/backups/

# Restore audit logs
cd /home/ryan/openclaw-orchestration-stack
tar -xzf data/backups/audit_logs_YYYYMMDD_HHMMSS.tar.gz

# Restore database (stop service first!)
sudo systemctl stop pred-market-arb.timer
tar -xzf data/backups/database_YYYYMMDD_HHMMSS.tar.gz -C data/
sudo systemctl start pred-market-arb.timer
```

---

## Common Issues

### Issue: Service fails with "Permission denied"

**Cause:** File permissions or systemd security settings

**Solution:**
```bash
# Fix ownership
sudo chown -R ryan:ryan /home/ryan/openclaw-orchestration-stack/data

# Check systemd security settings
sudo systemctl cat pred-market-arb.service | grep -E "(Protect|ReadWrite)"
```

### Issue: "ModuleNotFoundError" on startup

**Cause:** Python path not set or virtual environment not activated

**Solution:**
```bash
# Verify PYTHONPATH in service file
sudo systemctl cat pred-market-arb.service | grep PYTHONPATH

# Reinstall dependencies
cd /home/ryan/openclaw-orchestration-stack
pip3 install -r requirements.txt
```

### Issue: Timer not triggering

**Cause:** Timer not enabled or system time issues

**Solution:**
```bash
# Check timer status
systemctl list-timers pred-market-arb.timer

# Re-enable timer
sudo systemctl enable --now pred-market-arb.timer

# Check for trigger errors
journalctl -u pred-market-arb.timer
```

### Issue: Out of memory during scan

**Cause:** Scanner using too much memory

**Solution:**
```bash
# Edit service to increase memory limit
sudo systemctl edit pred-market-arb.service

# Add:
# [Service]
# MemoryMax=1G

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart pred-market-arb.timer
```

### Issue: Telegram alerts not sending

**Cause:** Missing or invalid Telegram credentials

**Solution:**
```bash
# Check .env file
grep TELEGRAM /home/ryan/openclaw-orchestration-stack/.env

# Test Telegram bot manually
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d "chat_id=<CHAT_ID>&text=Test message"
```

---

## Performance Tuning

### Reducing Scan Frequency

Edit the timer to run less frequently:

```bash
# Edit timer
sudo systemctl edit pred-market-arb.timer --full

# Change OnCalendar to hourly instead of daily:
# OnCalendar=hourly

# Reload
sudo systemctl daemon-reload
```

### Adjusting Resource Limits

```bash
# Edit service
sudo systemctl edit pred-market-arb.service

# Add overrides:
# [Service]
# CPUQuota=80%
# MemoryMax=1G
# TimeoutStartSec=600
```

---

## Docker Operations

### Docker Compose Commands

```bash
# Start all services
docker-compose -f deploy/docker_compose.yml up -d

# Start with monitoring
docker-compose -f deploy/docker_compose.yml --profile monitoring up -d

# View logs
docker-compose -f deploy/docker_compose.yml logs -f arb-scanner

# Run backup
docker-compose -f deploy/docker_compose.yml --profile backup run --rm backup

# Update images
docker-compose -f deploy/docker_compose.yml pull
docker-compose -f deploy/docker_compose.yml up -d

# Stop all services
docker-compose -f deploy/docker_compose.yml down
```

### Docker Health Checks

```bash
# Check container health
docker ps --filter "name=openclaw"

# Inspect health status
docker inspect --format='{{.State.Health.Status}}' openclaw-arb-scanner

# View health check logs
docker inspect --format='{{json .State.Health}}' openclaw-arb-scanner | jq
```

---

## Monitoring Setup

### Prometheus Metrics

Metrics are exposed at `http://localhost:9090/metrics` when monitoring profile is enabled.

### Grafana Dashboard

Access Grafana at `http://localhost:3000` (default credentials: admin/admin).

### Alerting Rules

Create alert rules in Prometheus for:
- Service down > 5 minutes
- Memory usage > 90%
- Disk space < 10%
- API errors > 10 in 1 hour

---

## Emergency Procedures

### Service Down

1. Check if process is running:
   ```bash
   ps aux | grep arb_scanner
   ```

2. Check for system resource issues:
   ```bash
   free -h
df -h
   ```

3. Restart service:
   ```bash
   sudo systemctl restart pred-market-arb.service
   ```

4. If still failing, check for corrupted data:
   ```bash
   # Backup current state
   python deploy/backup_script.py
   
   # Clear cache
   rm -rf /home/ryan/openclaw-orchestration-stack/data/cache/*
   
   # Restart
   sudo systemctl restart pred-market-arb.timer
   ```

### Data Corruption

1. Stop the service:
   ```bash
   sudo systemctl stop pred-market-arb.timer
   ```

2. Restore from backup:
   ```bash
   # List available backups
   ls -lt /home/ryan/openclaw-orchestration-stack/data/backups/
   
   # Restore
   tar -xzf /home/ryan/openclaw-orchestration-stack/data/backups/database_YYYYMMDD_HHMMSS.tar.gz
   ```

3. Restart service:
   ```bash
   sudo systemctl start pred-market-arb.timer
   ```

---

## Contact and Support

- **Issues:** https://github.com/openclaw/arb-hunter/issues
- **Documentation:** https://docs.openclaw.io
- **Emergency Contact:** ops@openclaw.io

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.2.1 | 2024-01 | Initial runbook |

---

*This runbook should be updated whenever operational procedures change.*
