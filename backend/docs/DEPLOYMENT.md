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

---

## 7. Active Cloud Deployments & Production Launch Verification

AURUMTRACE has been provisioned and verified on live cloud infrastructure:

### 7.1 Production Service Endpoints
- **Live Backend API (FastAPI + Render Oregon):** `https://aurumtrace-api-p1rr.onrender.com`
- **Interactive OpenAPI Documentation:** `https://aurumtrace-api-p1rr.onrender.com/docs`
- **Health Check Probe:** `https://aurumtrace-api-p1rr.onrender.com/health` (Returns HTTP 200 `{"status":"ok","version":"0.1.0","env":"production"}`)
- **Managed Database (PostgreSQL):** Render Managed PostgreSQL cluster (`dpg-dbhn1pmgekts73bnanc0-a`), database `aurumtrace` with Alembic head migrations (`0001_phase1`, `0002_phase2`)
- **Live Frontend (Vite + React + TypeScript on Vercel Edge):** `https://aurumtrace-web-gamma.vercel.app`

### 7.2 End-to-End Live Verification Summary
The production cloud environment was verified via an automated 15-step live audit (`scratch/run_live_e2e_verification.py`):
1. **Admin Authentication:** Authenticated as `admin@aurumtrace.com` (`Niharika Singh (Enterprise Admin)`).
2. **Karigar Hierarchy:** `PROD-K01` (Master Goldsmith Harish - Head Karigar) and `PROD-K02` (Setter Rajesh - Team Karigar).
3. **Job Order:** `J-0001` (Kundan Polki Bridal Choker 22K).
4. **Bullion Lot:** `L-0001` received into vault (100.000 g gross, 916.0 ppt fineness $\rightarrow$ 91.600 g fine gold).
5. **Vault Issuance:** 40.000 g gross (36.640 g fine gold) issued from `L-0001` to `PROD-K01`.
6. **Karigar Receipt Acknowledgement:** Verified and digitally acknowledged by Harish.
7. **Multi-level Transfer:** 15.000 g transferred from `PROD-K01` to `PROD-K02` for stone setting.
8. **Transfer Acknowledgement:** Verified and digitally signed by Rajesh.
9. **Manufacturing Measurement:** In-process stage measurement recorded (Input 15.000 g $\rightarrow$ Output 14.850 g on scale `SC-BENCH-02`).
10. **Vault Returns:**
    - Finished Jewellery: `RET-0001` (24.500 g gross, assayed at 912.0 ppt $\rightarrow$ 22.344 g fine gold).
    - Scrap from Harish: `RET-0002` (0.500 g gross, 916.0 ppt $\rightarrow$ 0.458 g fine gold).
    - Scrap from Rajesh: `RET-0003` (14.850 g gross, 916.0 ppt $\rightarrow$ 13.603 g fine gold).
    - Total Gross Metal Accounted: $24.500 + 0.500 + 14.850 = 39.850$ g (0.150 g setting loss).
11. **Deterministic Fine-Gold Reconciliation:** Run `REC-J-0001-v2` calculated exact fine gold balance (36.640 g issued vs 36.405 g accounted $\rightarrow$ 0.235 g unexplained variance, within 1.2% contractual allowance of 0.440 g).
12. **Exception Detection:** Laboratory fire assay shortfall simulated on `RET-0001` (890.0 ppt vs 916.0 ppt $\rightarrow$ 26.0 ppt deficit $\ge 20.0$ ppt threshold). Detected `EX-J-0001-V` (High variance) and `EX-J-0001-P-RET-0001` (Medium purity mismatch).
13. **AI Investigation Assistant:** Triggered for `EX-J-0001-V`. Analyzed discrepancy using read-only tools and generated evidence-grounded root cause findings (confidence 0.94).
14. **Commercial Settlement Rule & Worksheet:**
    - Rule `SR-0001`: Labour rate INR 450.00/g, Loss allowance 1.5%, Gold rate INR 6,800.00/g.
    - Worksheet `SW-0001`: Gross Labour INR 11,025.00, Gold Recovery deduction INR 2,271.20, Net Payable to Karigar INR 8,753.80.
15. **Formally Approved Settlement:** Submitted and formally approved by Enterprise Admin. Job `J-0001` transitioned to `settled`.

