# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# AURUMTRACE Backend Production Dockerfile
# Multi-stage, minimal, non-root user execution with Alembic migration entrypoint
# -----------------------------------------------------------------------------

FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------------------
# Final Production Runtime Stage
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS runner

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies from builder
COPY --from=builder /install /usr/local

# Create non-root application user
RUN groupadd -g 10001 aurum && \
    useradd -u 10001 -g aurum -m -s /bin/bash aurum

# Copy application source code and migrations
COPY --chown=aurum:aurum alembic.ini ./
COPY --chown=aurum:aurum alembic/ ./alembic/
COPY --chown=aurum:aurum app/ ./app/
COPY --chown=aurum:aurum scripts/ ./scripts/

# Create entrypoint runner
COPY --chown=aurum:aurum <<'EOF' /app/entrypoint.sh
#!/bin/sh
set -e

echo "[AURUMTRACE] Running database migrations..."
alembic upgrade head

echo "[AURUMTRACE] Starting API server on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips='*'
EOF

RUN chmod +x /app/entrypoint.sh

USER aurum

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
