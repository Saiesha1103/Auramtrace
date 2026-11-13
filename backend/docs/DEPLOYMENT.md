# AURUMTRACE — Production Deployment & Operations Guide

This guide details the production deployment, migration strategy, configuration, security hardening, and disaster recovery procedures for the AURUMTRACE backend service.

---

## 1. Production Architecture Overview

AURUMTRACE is an immutable, event-driven bullion accounting and jewelry manufacturing traceability engine.
In production:
- **Application Engine:** FastAPI on Python 3.13 / 3.14 running under `uvicorn` with multi-worker ASGI processes.
- **Source of Truth:** PostgreSQL 15+ with ACID transactions, append-only ledger tables (`material_events`, `audit_events`), and row-level locking (`SELECT ... FOR UPDATE`) on material lots during balance-altering transfers and returns.
- **Security Context:** Runs under a dedicated, unprivileged non-root operating system user (`aurum:aurum`, UID 10001).

---

## 2. Environment Variables & Production Hardening

All backend configuration variables are prefixed with `AURUM_`:

| Environment Variable | Production Required | Description | Example / Recommended |
|---|:---:|---|---|
| `AURUM_ENV` | **Yes** | Execution mode. Enforces security policies when set to `production`. | `production` |
| `AURUM_DATABASE_URL` | **Yes** | Connection string for PostgreSQL with `psycopg` driver. | `postgresql+psycopg://user:pass@pg-host:5432/aurumtrace_prod` |
| `AURUM_JWT_SECRET` | **Yes** | Cryptographic HMAC secret for signing authentication JWT tokens. Must be >= 48 bytes of entropy. | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `AURUM_ALLOW_REGISTRATION` | **Yes** | Disables public self-service organisation registration. Startup will abort if set to true in production. | `false` |
| `AURUM_CORS_ORIGINS` | **Yes** | Comma-delimited list of exact allowed browser origins for CORS. | `https://aurumtrace.yourcompany.com` |
| `AURUM_ACCESS_TOKEN_MINUTES` | No | Token expiration duration in minutes (default: 60). | `60` |
| `AURUM_SQL_ECHO` | No | Log raw SQL statements. Must remain `false` in production to prevent leaking sensitive ledger data. | `false` |

---

## 3. Deployment Methods

### Option A: Docker Compose (Single Host / Dedicated VM)

1. Generate a production environment file (`.env`):
   ```bash
   cat <<EOF > .env
   POSTGRES_USER=aurumtrace
   POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   POSTGRES_DB=aurumtrace_prod
   AURUM_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
   AURUM_CORS_ORIGINS=https://app.aurumtrace.com
   EOF
   ```

2. Start the production stack:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3. Verify health status:
   ```bash
   curl -i http://localhost:8000/health
   # Expected response: HTTP 200 {"status":"ok","env":"production","utc":"..."}
   ```

### Option B: Cloud Platforms (Render, AWS ECS, GCP Cloud Run)

1. **Database:** Provision a managed PostgreSQL instance (e.g. AWS RDS PostgreSQL or Render Managed Postgres).
2. **Container Image:** Build and publish the image using `backend/Dockerfile` to your container registry (Amazon ECR, Google Artifact Registry, or GitHub Packages).
3. **Environment:** Set `AURUM_ENV=production`, `AURUM_ALLOW_REGISTRATION=false`, `AURUM_JWT_SECRET`, and `AURUM_DATABASE_URL`.
4. **Health Check:** Point container health checks and load balancer liveness probes to `GET /health`.

---

## 4. Database Migrations & Zero-Downtime Strategy

Database migrations are managed via Alembic:

### Automated Migration at Startup
The production Docker entrypoint automatically executes `alembic upgrade head` before binding the uvicorn socket, ensuring tables and constraints exist.

### Migration Safety Rules
1. **Never alter existing `material_events` or `audit_events` columns.**
2. **Backward-compatible column additions:** All new columns must either be nullable or carry explicit server defaults.
3. **Batch table operations for SQLite:** For dev/testing environments, migrations utilize `batch_alter_table` to guarantee SQLite compatibility alongside PostgreSQL.
4. **Rollback verification:** Every migration file (`0001_phase1`, `0002_phase2`) includes thoroughly tested, reversible `downgrade()` routines.

Manual migration commands (if running outside Docker):
```bash
# Upgrade to latest
alembic upgrade head

# Check status
alembic current

# Rollback one migration
alembic downgrade -1
```

---

## 5. Synthetic Demo Data Seeding (Staging / QA)

To seed a complete, realistic dataset for demonstration, user acceptance testing, or training:
```bash
python -m scripts.seed
```
This provisions:
- Vault operator, production manager, and admin users.
- Full karigar network with hierarchy (Heads, Karigars, Subcontractors).
- Multi-level material transfers, acknowledgements, and a compensating reversal.
- Production entries across manufacturing stages with physical measurements.
- Material returns (finished jewellery with stones, scrap, and assay shortfalls).
- 4 Reconciled jobs with diverse outcomes (`within_allowance`, `above_allowance`, `fineness_mismatch`, `unacknowledged_transfer`).
- Exception lifecycle cases, attached evidence, and a deterministic AI investigation run.
- Commercial settlement rules and an approved settlement worksheet.

The seed script is **fully idempotent**: running it multiple times will safely detect existing data and exit without duplication.

---

## 6. Backup and Disaster Recovery

### Automated PostgreSQL Dumps
Schedule daily logical backups with `pg_dump`:
```bash
docker exec -t aurumtrace-pg-prod pg_dump -U aurumtrace -Fc aurumtrace_prod > aurumtrace_backup_$(date +%Y%m%d_%H%M%S).dump
```

### Restore Procedure
```bash
# Terminate existing connections and restore
docker exec -i aurumtrace-pg-prod pg_restore -U aurumtrace -d aurumtrace_prod --clean --if-exists < aurumtrace_backup.dump
```
