# Setup Guide

## Quick Start (5 Minutes)

Get OpenClaw running locally in 5 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/openclaw-orchestration-stack/openclaw-orchestration-stack.git
cd openclaw-orchestration-stack

# 2. Copy environment file
cp .env.example .env

# 3. Add your API keys to .env
# Edit .env and add at minimum: ANTHROPIC_API_KEY

# 4. Start with Docker Compose
docker-compose up -d

# 5. Verify installation
curl http://localhost:8000/health
```

**Expected Output:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "api": "healthy",
    "router": "healthy",
    "intent_classifier": "healthy"
  }
}
```

## Full Installation Guide

### Prerequisites

#### Required

- **Python 3.11+** — For OpenClaw and DevClaw
- **Node.js 18+** — For n8n
- **Git** — For repository operations
- **Docker & Docker Compose** — Recommended deployment method

#### Optional

- **Rust** — If working with Rust repositories
- **Node.js/npm** — If working with Node.js repositories
- **PostgreSQL** — Alternative to SQLite for production

### Step 1: System Dependencies

#### Ubuntu/Debian

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install Git
sudo apt install -y git

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

#### macOS

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 node git

# Install Docker Desktop
brew install --cask docker
```

#### Windows (WSL2)

```powershell
# Install WSL2
wsl --install -d Ubuntu

# Then follow Ubuntu instructions inside WSL2
```

### Step 2: Clone Repository

```bash
# Clone with SSH
git clone git@github.com:openclaw-orchestration-stack/openclaw-orchestration-stack.git

# Or clone with HTTPS
git clone https://github.com/openclaw-orchestration-stack/openclaw-orchestration-stack.git

cd openclaw-orchestration-stack
```

### Step 3: Python Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env  # or use your preferred editor
```

**Required Variables:**

```bash
# API Keys (at least one required)
ANTHROPIC_API_KEY="sk-ant-api03-..."
# OPENAI_API_KEY="sk-..."

# Database
OPENCLAW_DB_PATH="data/openclaw.db"

# GitHub (for PR management)
GITHUB_API_KEY="ghp_..."
GITHUB_WEBHOOK_SECRET="your-webhook-secret"

# API Configuration
OPENCLAW_API_KEY="your-secure-api-key"
PORT=8000
```

### Step 5: Database Initialization

```bash
# Create data directory
mkdir -p data

# Run migrations
python shared/migrations/runner.py migrate

# Verify database
cat > /tmp/test_db.py << 'EOF'
from shared.db import execute, get_connection

# Test connection
with get_connection() as conn:
    cursor = conn.execute("SELECT 1")
    print("Database connection: OK")

# Check tables
tables = execute("SELECT name FROM sqlite_master WHERE type='table'")
print(f"Tables: {[t['name'] for t in tables]}")
EOF

python /tmp/test_db.py
```

### Step 6: n8n Setup

```bash
# Install n8n globally
npm install -g n8n

# Create n8n configuration directory
mkdir -p ~/.n8n

# Set n8n environment variables
export N8N_BASIC_AUTH_ACTIVE=true
export N8N_BASIC_AUTH_USER=admin
export N8N_BASIC_AUTH_PASSWORD=your-secure-password
export N8N_HOST=localhost
export N8N_PORT=5678

# Start n8n
n8n
```

Access n8n at http://localhost:5678

### Step 7: GitHub Integration (Optional)

#### Create GitHub App

1. Go to GitHub Settings → Developer Settings → GitHub Apps
2. Click "New GitHub App"
3. Configure:
   - **GitHub App Name:** `OpenClaw Bot`
   - **Homepage URL:** Your repository URL
   - **Webhook URL:** `https://your-domain.com/webhooks/github`
   - **Webhook Secret:** Generate a secure random string
4. Permissions:
   - Repository: Read & Write (for PRs, issues)
   - Pull Requests: Read & Write
   - Issues: Read & Write
   - Contents: Read & Write
5. Subscribe to events:
   - Pull request
   - Pull request review
   - Issue comment

#### Configure Webhook

```bash
# Add webhook secret to .env
GITHUB_WEBHOOK_SECRET="your-generated-secret"
```

### Step 8: Start Services

#### Option A: Manual Start

```bash
# Terminal 1: Start OpenClaw API
python -m openclaw.src.api

# Terminal 2: Start DevClaw Worker
python -m devclaw_runner.src.worker

# Terminal 3: Start Symphony Bridge
python -m symphony_bridge.src.webhook_handler

# Terminal 4: Start n8n
n8n
```

#### Option B: Using Make

```bash
# Start all services
make start

# Start individual services
make start-api
make start-worker
make start-n8n
```

#### Option C: Docker Compose (Recommended)

```bash
# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Step 9: Verify Installation

```bash
# Test API health
curl http://localhost:8000/health

# Test intent classification
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "type": "feature_request",
      "description": "Add user authentication"
    }
  }'

# Check n8n
curl http://localhost:5678/healthz
```

### Step 10: Configure Repository

Create `.openclaw/review.yaml` in your target repository:

```bash
cd /path/to/your/repo
mkdir -p .openclaw
cat > .openclaw/review.yaml << 'EOF'
repo:
  language: mixed
  profile_default: STANDARD

commands:
  test:
    - "pytest -q"
  lint:
    - "ruff check ."
  format:
    - "black ."

security:
  dependency_scan:
    - "pip-audit -r requirements.txt"
  secret_scan:
    - "gitleaks detect --no-git -v"
EOF
```

## Development Setup

### Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=openclaw --cov=devclaw_runner --cov=symphony_bridge

# Run specific test file
pytest tests/unit/test_openclaw.py

# Run with verbose output
pytest -v
```

### Code Quality Tools

```bash
# Format code
make format

# Run linting
make lint

# Run type checking
make type-check

# Run all checks
make check
```

## Production Deployment

### Environment Variables

```bash
# Production .env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database
OPENCLAW_DB_PATH=/var/lib/openclaw/data.db

# Security
OPENCLAW_API_KEY="strong-random-key"
ALLOWED_ORIGINS="https://your-domain.com"

# Workers
MAX_WORKERS=10
TASK_TIMEOUT=300
```

### Systemd Service

See [systemd/openclaw.service](../../systemd/openclaw.service)

### Docker Production

```bash
# Production compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Database Backup

```bash
# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups/openclaw"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_PATH="/var/lib/openclaw/data.db"

# Create backup
sqlite3 "$DB_PATH" ".backup '${BACKUP_DIR}/backup_${TIMESTAMP}.db'"

# Compress
gzip "${BACKUP_DIR}/backup_${TIMESTAMP}.db"

# Keep only last 7 days
find "$BACKUP_DIR" -name "backup_*.db.gz" -mtime +7 -delete
```

## Troubleshooting Installation

### Python Version Issues

```bash
# Check Python version
python3 --version  # Should be 3.11+

# If wrong version, specify explicitly
python3.11 -m venv venv
```

### Permission Denied

```bash
# Fix permissions
sudo chown -R $USER:$USER data/
chmod 755 data/
```

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
PORT=8001 python -m openclaw.src.api
```

### Database Locked

```bash
# Check for WAL files
ls -la data/*.db-*

# If stuck, restart services
docker-compose restart

# Or manually remove WAL (data loss risk!)
rm data/*.db-wal data/*.db-shm
```

### n8n Connection Refused

```bash
# Check if n8n is running
ps aux | grep n8n

# Check logs
n8n

# Reset n8n
rm -rf ~/.n8n
n8n
```

## Next Steps

- [Configuration Guide](./configuration.md) — Configure all options
- [Security Guide](./security.md) — Security best practices
- [API Documentation](../api/rest-api.md) — API reference
- [Troubleshooting](./troubleshooting.md) — Common issues
