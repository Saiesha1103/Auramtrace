# AURUMTRACE backend (Phase 1 foundation)

FastAPI + PostgreSQL + SQLAlchemy 2 + Pydantic 2. Fine-gold chain of custody with an **append-only** material event ledger.

- API reference with real request/response examples: [`docs/API.md`](docs/API.md)
- Handoff for the next phase: [`docs/HANDOFF.md`](docs/HANDOFF.md)
- Swagger UI: http://localhost:8000/docs (ReDoc: `/redoc`)

## Quick start (Windows / Git Bash; adapt paths for macOS/Linux)

```bash
cd backend
py -m venv .venv                      # python3 -m venv .venv on macOS/Linux
./.venv/Scripts/python -m pip install -r requirements-dev.txt
cp .env.example .env                  # local dev settings
docker compose -f docker-compose.dev.yml up -d   # Postgres 17 on localhost:5433
./.venv/Scripts/python -m alembic upgrade head   # create schema + append-only triggers
./.venv/Scripts/python -m scripts.seed           # SYNTHETIC demo org, users, karigars, jobs, lots
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Demo logins are synthetic and listed in `scripts/seed.py` (development only).

## Tests

```bash
./.venv/Scripts/python -m pytest                                   # SQLite (fast, no services)
AURUM_TEST_DATABASE_URL=postgresql+psycopg://aurumtrace:aurumtrace_dev@localhost:5433/aurumtrace_test \
  ./.venv/Scripts/python -m pytest                                 # PostgreSQL (CI should use this)
```

64 tests: fine-gold maths (PRD Appendix A), models & constraints, auth/roles/org isolation, karigar & job APIs, issuance/acknowledgement workflows, and history protection (ORM guard, DB triggers, no mutation routes, reversals).

## Layout

```
app/
  main.py          app factory, CORS, routers, /health, Swagger
  config.py        AURUM_* settings (pydantic-settings), production guards
  database.py      engine/session, get_db dependency
  errors.py        one error envelope {"error": {code, message, details}}
  deps.py          bearer auth, role guards (Admin / Manager / VaultOperator)
  models/          entities.py (7 tables), enums.py, __init__ (append-only guards + trigger DDL)
  schemas/         camelCase request/response models, Grams/Fineness types
  services/        fine_gold, ledger (derived balances), custody (lot/issue/ack/reverse), views, audit, security, codes
  routers/         auth, organisations (+users, audit), karigars, jobs, lots, events
alembic/           migrations (0001 baseline includes triggers)
scripts/seed.py    synthetic development data
tests/             pytest suite
```

## Rules the code enforces

- Gross, net metal and fineness are stored separately; `fine = net × fineness ÷ 1000` (Decimal, half-up, 0.001 g).
- `material_events` and `audit_events` are append-only: ORM flush guard **and** database triggers (PostgreSQL & SQLite). No update/delete endpoints.
- Corrections are `reversal` events that mirror the original; balances are the sum of all movement events.
- Balances (vault, karigar, job) are always derived from events — there is no mutable balance column.
- Every query is organisation-scoped; roles gate every write; every write is audited.
