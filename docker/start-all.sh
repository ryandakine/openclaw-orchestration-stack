#!/bin/bash
# Start all OpenClaw services in a single container
# Used for demo/small deployments

set -e

echo "🚀 Starting OpenClaw Orchestration Stack..."

# Create necessary directories
mkdir -p /app/data /app/logs /home/openclaw/.n8n

# Start n8n in background
echo "📡 Starting n8n..."
export N8N_USER_FOLDER=/home/openclaw/.n8n
n8n &
N8N_PID=$!

# Wait for n8n to be ready
echo "⏳ Waiting for n8n..."
until curl -s http://localhost:5678/healthz > /dev/null 2>&1; do
    sleep 2
done
echo "✅ n8n is ready!"

# Start worker in background
echo "⚡ Starting DevClaw worker..."
python -m devclaw_runner.src.worker &
WORKER_PID=$!

# Wait for database to be ready
echo "⏳ Initializing database..."
python shared/migrations/runner.py migrate || true

# Start API server
echo "🎯 Starting OpenClaw API..."
exec uvicorn openclaw.src.api:app --host 0.0.0.0 --port 8000
