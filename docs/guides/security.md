# Security Guide

## Overview

Security is a core principle of the OpenClaw Orchestration Stack. This guide covers security best practices, configuration, and procedures for running OpenClaw securely.

## Security Model

### Threat Model

**In Scope:**
- Unauthorized API access
- Code injection through task payloads
- Data exfiltration
- Privilege escalation
- Replay attacks
- Webhook spoofing

**Out of Scope:**
- Physical server security
- Network infrastructure security
- Client-side security (assumes trusted clients)

### Security Layers

```
┌─────────────────────────────────────────┐
│         Application Security            │
│  - Input validation, SQL injection      │
├─────────────────────────────────────────┤
│         Authentication/Authorization    │
│  - API keys, JWT tokens, OAuth          │
├─────────────────────────────────────────┤
│         Network Security                │
│  - TLS, CORS, rate limiting             │
├─────────────────────────────────────────┤
│         Infrastructure Security         │
│  - Secrets management, file perms       │
├─────────────────────────────────────────┤
│         Audit & Monitoring              │
│  - Logging, alerting, audit trail       │
└─────────────────────────────────────────┘
```

## Authentication

### API Key Authentication

**Generating Secure API Keys:**

```bash
# Generate cryptographically secure key
openssl rand -hex 32

# Or using Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Configuration:**

```bash
# .env
OPENCLAW_API_KEY="your-secure-64-char-hex-key"
```

**Usage:**

```bash
curl -H "X-API-Key: $OPENCLAW_API_KEY" \
  http://localhost:8000/ingest \
  -d '{"payload": {"type": "test"}}'
```

### JWT Authentication (Optional)

```python
# Enable JWT
JWT_SECRET="your-jwt-signing-secret"
JWT_EXPIRY=3600

# Generate token
import jwt
token = jwt.encode(
    {"sub": "user123", "exp": time.time() + 3600},
    JWT_SECRET,
    algorithm="HS256"
)
```

### GitHub Authentication

**Personal Access Token (PAT):**

1. Go to GitHub Settings → Developer Settings → Personal Access Tokens
2. Generate new token with scopes:
   - `repo` — Full repository access
   - `workflow` — Update GitHub Actions workflows
   - `read:org` — Read org membership

**GitHub App (Recommended for Production):**

```bash
# Generate private key
openssl genrsa -out github-app.pem 4096

# Configuration
GITHUB_APP_ID="123456"
GITHUB_PRIVATE_KEY_PATH="/secrets/github-app.pem"
```

## Authorization

### Role-Based Access Control (RBAC)

```yaml
# config/rbac.yaml
roles:
  admin:
    permissions:
      - "*"
  
  developer:
    permissions:
      - "tasks:read"
      - "tasks:create"
      - "tasks:retry"
    denied:
      - "admin:*"
  
  reviewer:
    permissions:
      - "tasks:read"
      - "reviews:create"
      - "reviews:update"

users:
  - user: alice@example.com
    roles: [admin]
  - user: bob@example.com
    roles: [developer]
```

### Repository-Level Permissions

```yaml
# .openclaw/review.yaml
permissions:
  allowed_users:
    - "alice"
    - "bob"
  
  allowed_teams:
    - "engineering"
  
  require_approval_from:
    - "tech-leads"
  
  protected_branches:
    - main
    - production
```

## Input Validation

### Request Validation

```python
from pydantic import BaseModel, Field, validator
from typing import Optional
import re

class IngestRequest(BaseModel):
    payload: dict
    request_id: Optional[str] = Field(default=None, max_length=64)
    priority: int = Field(default=5, ge=1, le=10)
    
    @validator('request_id')
    def validate_request_id(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid request_id format')
        return v
    
    @validator('payload')
    def validate_payload_size(cls, v):
        import json
        if len(json.dumps(v)) > 100000:  # 100KB limit
            raise ValueError('Payload too large')
        return v
```

### SQL Injection Prevention

All database queries use parameterized statements:

```python
# SAFE - Parameterized query
execute(
    "SELECT * FROM tasks WHERE id = ? AND status = ?",
    (task_id, status)
)

# UNSAFE - Never do this!
execute(f"SELECT * FROM tasks WHERE id = '{task_id}'")
```

### Command Injection Prevention

```python
import shlex
from pathlib import Path

# SAFE - Validate and sanitize
allowed_commands = {'pytest', 'cargo', 'npm'}

def run_test(command: str, work_dir: str):
    # Validate work_dir is within allowed path
    work_path = Path(work_dir).resolve()
    allowed_path = Path('/tmp/devclaw').resolve()
    if not str(work_path).startswith(str(allowed_path)):
        raise SecurityError("Invalid work directory")
    
    # Validate command
    cmd_parts = shlex.split(command)
    if cmd_parts[0] not in allowed_commands:
        raise SecurityError("Command not allowed")
    
    # Run with timeout and sandbox
    subprocess.run(cmd_parts, cwd=work_dir, timeout=300)
```

## Webhook Security

### Signature Verification

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    # Extract signature
    if '=' in signature:
        _, sig = signature.split('=', 1)
    else:
        sig = signature
    
    # Compute expected signature
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison
    return hmac.compare_digest(expected, sig)
```

### IP Whitelisting

```python
# GitHub webhook IPs (check https://api.github.com/meta for current list)
GITHUB_HOOK_IPS = [
    '140.82.112.0/20',
    '185.199.108.0/22',
    # ...
]

def is_github_ip(ip: str) -> bool:
    import ipaddress
    client_ip = ipaddress.ip_address(ip)
    for cidr in GITHUB_HOOK_IPS:
        if client_ip in ipaddress.ip_network(cidr):
            return True
    return False
```

## Secrets Management

### Environment Variables

```bash
# .env file (add to .gitignore!)
ANTHROPIC_API_KEY="sk-ant-api03-..."
GITHUB_API_KEY="ghp_..."
OPENCLAW_API_KEY="..."
```

### Docker Secrets

```yaml
# docker-compose.yml
secrets:
  anthropic_api_key:
    file: ./secrets/anthropic_api_key.txt
  github_api_key:
    file: ./secrets/github_api_key.txt

services:
  openclaw:
    secrets:
      - anthropic_api_key
      - github_api_key
    environment:
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_api_key
```

### HashiCorp Vault

```python
import hvac
import os

client = hvac.Client(url='https://vault.example.com')
client.auth.token_login(os.environ['VAULT_TOKEN'])

# Read secrets
secret = client.secrets.kv.v2.read_secret_version(
    path='openclaw/api-keys'
)

anthropic_key = secret['data']['data']['anthropic']
```

### AWS Secrets Manager

```python
import boto3
from botocore.exceptions import ClientError

def get_secret(secret_name: str) -> str:
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        raise SecurityError(f"Failed to retrieve secret: {e}")
```

## Encryption

### At-Rest Encryption

**Database Encryption (SQLCipher):**

```bash
# Build SQLCipher
./configure --enable-tempstore=yes \
  CFLAGS="-DSQLITE_HAS_CODEC" \
  LDFLAGS="-lcrypto"
make && make install

# Encrypt database
sqlcipher data/openclaw.db
sqlite> PRAGMA key = 'your-encryption-key';
sqlite> ATTACH DATABASE 'plaintext.db' AS plaintext KEY '';
sqlite> SELECT sqlcipher_export('plaintext');
sqlite> DETACH DATABASE plaintext;
```

**Application-Level Encryption:**

```python
from cryptography.fernet import Fernet

# Generate key
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt sensitive data
encrypted = cipher.encrypt(b"sensitive data")

# Decrypt
decrypted = cipher.decrypt(encrypted)
```

### In-Transit Encryption

**TLS Configuration:**

```python
# Using uvicorn with TLS
uvicorn.run(
    app,
    host="0.0.0.0",
    port=443,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem",
    ssl_ca_certs="/path/to/ca.pem"
)
```

**Reverse Proxy (nginx):**

```nginx
server {
    listen 443 ssl http2;
    server_name openclaw.example.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Network Security

### CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],  # Not "*"
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    max_age=600
)
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/ingest")
@limiter.limit("10/minute")
async def ingest(request: Request):
    pass
```

### IP Whitelisting

```python
ALLOWED_IPS = {'10.0.0.0/8', '172.16.0.0/12'}

@app.middleware("http")
async def ip_whitelist(request: Request, call_next):
    client_ip = request.client.host
    if not any(
        ipaddress.ip_address(client_ip) in ipaddress.ip_network(cidr)
        for cidr in ALLOWED_IPS
    ):
        raise HTTPException(403, "IP not allowed")
    return await call_next(request)
```

## Audit Logging

### Security Events

```python
# Log security-relevant events
from openclaw.src.audit import log_audit_event

# Authentication events
log_audit_event(
    correlation_id=corr_id,
    actor="user123",
    action="auth.login",
    payload={"ip": client_ip, "success": True}
)

# Authorization events
log_audit_event(
    correlation_id=corr_id,
    actor="user123",
    action="auth.access_denied",
    payload={"resource": "admin/tasks", "reason": "insufficient_permissions"}
)

# Data access events
log_audit_event(
    correlation_id=corr_id,
    actor="user123",
    action="data.access",
    payload={"table": "tasks", "operation": "SELECT", "rows": 10}
)
```

### Audit Log Retention

```bash
# Archive old audit logs
#!/bin/bash
ARCHIVE_DIR="/var/log/openclaw/archive"
DB_PATH="/var/lib/openclaw/openclaw.db"

# Export logs older than 90 days
sqlite3 "$DB_PATH" <<EOF
.mode csv
.output ${ARCHIVE_DIR}/audit_$(date +%Y%m%d).csv
SELECT * FROM audit_events 
WHERE timestamp < datetime('now', '-90 days');
EOF

# Compress
gzip ${ARCHIVE_DIR}/audit_*.csv

# Delete from database
sqlite3 "$DB_PATH" "DELETE FROM audit_events WHERE timestamp < datetime('now', '-90 days');"
```

## Vulnerability Management

### Dependency Scanning

```bash
# Python dependencies
pip-audit -r requirements.txt

# JavaScript dependencies
cd n8n-workflows && npm audit

# Check for known vulnerabilities
safety check
```

### Container Scanning

```bash
# Scan Docker image
docker scan openclaw:latest

# Or use Trivy
trivy image openclaw:latest
```

### Security Updates

```bash
# Check for updates
pip list --outdated

# Update dependencies
pip install -U -r requirements.txt

# Test updates
pytest

# Deploy updates
docker-compose up -d --build
```

## Incident Response

### Security Incident Checklist

1. **Contain**
   ```bash
   # Disable API keys
   docker-compose exec openclaw python -c "
   from shared.db import execute
   execute('UPDATE api_keys SET disabled = 1')
   "
   
   # Block suspicious IPs
   iptables -A INPUT -s <IP> -j DROP
   ```

2. **Investigate**
   ```bash
   # Check audit logs
   sqlite3 data/openclaw.db "SELECT * FROM audit_events WHERE timestamp > datetime('now', '-1 hour')"
   
   # Check access logs
   grep "suspicious-pattern" logs/access.log
   ```

3. **Recover**
   ```bash
   # Rotate compromised credentials
   # Update all API keys
   # Review and revoke OAuth tokens
   ```

4. **Post-Incident**
   - Document the incident
   - Update security measures
   - Conduct post-mortem

### Breach Notification

If a data breach occurs:

1. Assess scope within 24 hours
2. Notify affected users within 72 hours
3. Document remediation steps
4. Report to relevant authorities if required

## Compliance

### SOC 2 Considerations

- **CC6.1**: Logical access security — Implemented via API keys and RBAC
- **CC6.2**: Access removal — Automated offboarding via API key revocation
- **CC7.2**: System monitoring — Comprehensive audit logging
- **CC8.1**: Change management — PR-based changes with mandatory review

### GDPR Compliance

```python
# Data export (right to portability)
def export_user_data(user_id: str) -> dict:
    tasks = execute("SELECT * FROM tasks WHERE created_by = ?", (user_id,))
    reviews = execute("SELECT * FROM reviews WHERE reviewer_id = ?", (user_id,))
    return {"tasks": tasks, "reviews": reviews}

# Data deletion (right to be forgotten)
def delete_user_data(user_id: str):
    execute("DELETE FROM tasks WHERE created_by = ?", (user_id,))
    execute("DELETE FROM audit_events WHERE actor = ?", (user_id,))
```

## Security Checklist

### Deployment Checklist

- [ ] API keys generated with cryptographically secure random
- [ ] TLS enabled for all communications
- [ ] Webhook secrets configured and verified
- [ ] Database file permissions set to 600
- [ ] Secrets stored in secure vault (not in code)
- [ ] Rate limiting enabled
- [ ] CORS configured with specific origins
- [ ] Audit logging enabled
- [ ] Automated backups configured
- [ ] Monitoring and alerting configured

### Regular Maintenance

- [ ] Rotate API keys every 90 days
- [ ] Review access logs weekly
- [ ] Update dependencies monthly
- [ ] Run security scans monthly
- [ ] Review and prune old audit logs
- [ ] Test incident response procedures quarterly

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [GitHub Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
