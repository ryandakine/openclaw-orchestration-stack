# OpenClaw Orchestration Stack Dockerfile
# Multi-stage build for production deployment

# ==============================================================================
# Stage 1: Base Python Image
# ==============================================================================
FROM python:3.11-slim-bookworm as python-base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    sqlite3 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# Stage 2: Node.js Base Image
# ==============================================================================
FROM node:18-bookworm-slim as node-base

# Install n8n globally
RUN npm install -g n8n@1.0.0

# ==============================================================================
# Stage 3: Builder
# ==============================================================================
FROM python-base as builder

# Install Poetry
RUN pip install poetry==1.7.0

# Copy dependency files
WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# Install dependencies (without dev dependencies)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --without dev \
    && rm -rf $POETRY_CACHE_DIR

# ==============================================================================
# Stage 4: Development
# ==============================================================================
FROM python-base as development

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.7.0

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install all dependencies (including dev)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy source code
COPY . .

# Install project
RUN poetry install --no-interaction --no-ansi

# Expose port
EXPOSE 8000

# Run in development mode
CMD ["poetry", "run", "uvicorn", "openclaw.src.api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ==============================================================================
# Stage 5: Production
# ==============================================================================
FROM python-base as production

# Create non-root user
RUN groupadd -r openclaw && useradd -r -g openclaw openclaw

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/config \
    && chown -R openclaw:openclaw /app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=openclaw:openclaw openclaw/ ./openclaw/
COPY --chown=openclaw:openclaw devclaw-runner/ ./devclaw-runner/
COPY --chown=openclaw:openclaw symphony-bridge/ ./symphony-bridge/
COPY --chown=openclaw:openclaw shared/ ./shared/
COPY --chown=openclaw:openclaw config/ ./config/

# Set permissions
RUN chmod 755 /app/data /app/logs

# Switch to non-root user
USER openclaw

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run production server
CMD ["uvicorn", "openclaw.src.api:app", "--host", "0.0.0.0", "--port", "8000"]

# ==============================================================================
# Stage 6: Worker
# ==============================================================================
FROM production as worker

# Install additional tools for workers
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    cargo \
    && rm -rf /var/lib/apt/lists/*

USER openclaw

# Worker entry point
CMD ["python", "-m", "devclaw_runner.src.worker"]

# ==============================================================================
# Stage 7: n8n
# ==============================================================================
FROM node-base as n8n

# Create non-root user
RUN groupadd -r n8n && useradd -r -g n8n n8n

# Create n8n directory
RUN mkdir -p /home/n8n/.n8n && chown -R n8n:n8n /home/n8n

USER n8n

# Expose n8n port
EXPOSE 5678

# Environment variables
ENV N8N_USER_FOLDER=/home/n8n/.n8n

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5678/healthz || exit 1

# Start n8n
CMD ["n8n"]

# ==============================================================================
# Stage 8: All-in-One (for demo/small deployments)
# ==============================================================================
FROM python-base as all-in-one

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install n8n
RUN npm install -g n8n@1.0.0

# Create non-root user
RUN groupadd -r openclaw && useradd -r -g openclaw openclaw

# Create directories
RUN mkdir -p /app/data /app/logs /app/config /home/openclaw/.n8n \
    && chown -R openclaw:openclaw /app /home/openclaw

WORKDIR /app

# Copy installed packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=openclaw:openclaw . .

# Install project
RUN pip install -e . --no-deps

# Setup scripts
COPY --chown=openclaw:openclaw docker/start-all.sh /app/start-all.sh
RUN chmod +x /app/start-all.sh

USER openclaw

# Expose ports
EXPOSE 8000 5678

# Start all services
CMD ["/app/start-all.sh"]
