# Backend handoff — Phase 1 (Utkarsh) → Phase 2 (Niharika)

Branch: `feat/backend-foundation` (from `feat/landing-page` @ `1cf4a76`). Everything lives in `backend/`.
Source of truth for behaviour: the AURUMTRACE Research & Product Blueprint (PRD) §3, §6–§9, Appendix A/B.

## 1. Completed modules

| Module | Where | Status |
|---|---|---|
| Config (env-based, prod guards) | `app/config.py`, `.env.example` | ✅ |
| DB engine/session, Alembic baseline | `app/database.py`, `alembic/versions/0001_phase1_*` | ✅ upgrade/downgrade verified on PostgreSQL 17; `alembic check` clean |
| Models: Organisation, User, Karigar, JobOrder, MaterialLot, MaterialEvent, AuditEvent | `app/models/entities.py` | ✅ FKs, unique codes per org, CHECK constraints |
| Append-only history | `app/models/__init__.py` + migration | ✅ ORM guard + PG/SQLite triggers on `material_events`, `audit_events` |
| Fine-gold arithmetic | `app/services/fine_gold.py` | ✅ Decimal, 0.001 g, half-up; PRD Appendix A test |
| Ledger (derived balances, follow-ups) | `app/services/ledger.py` | ✅ vault / karigar / job / lot balances from events only |
| Custody ops: receive lot, issue, acknowledge, reverse | `app/services/custody.py` | ✅ balance checks, row lock per lot (PG), audit |
| Auth (JWT bearer, bcrypt) + roles | `app/services/security.py`, `app/deps.py`, `routers/auth.py` | ✅ admin / manager / vault_operator / viewer |
| Organisation & users, audit read | `routers/organisations.py` | ✅ |
| Karigars: create, list/filter, profile (custody), hierarchy, update | `routers/karigars.py` | ✅ |
| Jobs: create, list/filter, detail, edit/cancel | `routers/jobs.py` | ✅ |
| Lots & issuance, events history, acknowledge, reverse | `routers/lots.py`, `routers/events.py` | ✅ |
| Error envelope | `app/errors.py` | ✅ `{"error": {code, message, details}}` everywhere |
| Synthetic seed (mirrors frontend demo data) | `scripts/seed.py` | ✅ idempotent |
| Tests (64) | `tests/` | ✅ pass on SQLite **and** PostgreSQL |
| API reference with captured examples | `docs/API.md`, Swagger `/docs` | ✅ |

## 2. Database schema

```
organisations (id PK, name, created_at)
users         (id PK, organisation_id FK, email UNIQUE, full_name, role, password_hash, is_active, created_at)
karigars      (id PK, organisation_id FK, code, name, kind, head_karigar_id FK→karigars, unit, contact, skills JSON, status, created_at)
              UNIQUE(organisation_id, code); CHECK head ≠ self
job_orders    (id PK, organisation_id FK, code, title, order_ref, process, karat, target_fineness_ppt, pieces, target_gross_per_piece_g,
               loss_allowance_pct, contract_version, head_karigar_id FK→karigars, due_date, notes, status, created_by_id FK→users, created_at)
              UNIQUE(organisation_id, code); CHECK pieces>0; CHECK 0≤allowance≤5
material_lots (id PK, organisation_id FK, code, metal_type, source, gross_weight_g, net_weight_g, stone_weight_g, fineness_ppt, fine_gold_g,
               source_job_id FK→job_orders, created_by_id FK→users, created_at)
              UNIQUE(organisation_id, code); CHECK net≤gross; CHECK 0<fineness≤999.9
material_events  ── APPEND-ONLY ──
              (id PK, organisation_id FK, event_type, lot_id FK, job_id FK,
               from_type, from_karigar_id FK, to_type, to_karigar_id FK,          -- custodians: external | vault | karigar
               gross_weight_g, net_weight_g, fineness_ppt, fine_gold_g,          -- NULL for non-movement events
               scale_id, operator_name, measurement_method, challan_ref, evidence_ref, note,
               ref_event_id FK→material_events, acknowledged_by_name,
               occurred_at, recorded_at, recorded_by_id FK→users)
              UNIQUE(ref_event_id, event_type)  -- one acknowledgement / one reversal per event
audit_events  ── APPEND-ONLY ── (id PK, organisation_id FK, actor_user_id FK, action, entity_type, entity_id, details JSON, created_at)
```

Weights `NUMERIC(14,3)` grams; fineness `NUMERIC(5,1)` ppt. Enums are stored as plain strings (no DB enum types) so new values need no type migration.

**Balance model.** Movement events (`lot_received`, `issue`, `reversal`) carry quantities and from/to custodians. A custodian's balance = Σ(to) − Σ(from) over all movement rows. A reversal is the mirror of the row it corrects, so nothing is ever filtered or edited. Fine gold is computed from the **net** balance per lot × the lot's fineness (no rounding drift).

## 3. API endpoints

Full list, permission matrix and real request/response examples: **[`docs/API.md`](API.md)**. Summary:

`/api/v1/auth/{register,login,me}` · `/organisations/me` · `/users`, `/users/{id}` · `/audit` · `/karigars`, `/karigars/hierarchy`, `/karigars/{id}` · `/jobs`, `/jobs/{id}` · `/lots`, `/lots/{id}`, `/lots/{id}/issue` · `/events`, `/events/{id}`, `/events/{id}/acknowledge`, `/events/{id}/reverse` · `/health`

## 4. Environment setup

See [`README.md`](../README.md#quick-start-windows--git-bash-adapt-paths-for-macoslinux). Short version: Python 3.12+ (tested 3.14), `pip install -r requirements-dev.txt`, `docker compose -f docker-compose.dev.yml up -d`, `alembic upgrade head`, `python -m scripts.seed`, `uvicorn app.main:app --reload`.
Note: a dev container named `aurumtrace-pg-dev` may already exist from Phase 1 setup (created with `docker run`); remove it (`docker rm -f aurumtrace-pg-dev`) before using the compose file, or keep using it — same port and credentials.

## 5. Frontend compatibility notes

- The frontend is **Vite + React + TypeScript** (not Next.js); it runs on `http://localhost:5173`, already allowed by CORS.
- Frontend data boundary: `src/app/data/api.ts` (reads `VITE_API_BASE_URL`; currently reports "not connected" and the app uses synthetic data). Point it at `http://localhost:8000/api/v1`.
- Units differ today: frontend fineness is a fraction (0.916) → API is ppt (916.0). Role/kind/status labels map to snake_case enums (see API.md).
- Frontend `Transfer`, `ProductionEntry`, `ReturnEntry`, settlement and AI types have **no backend yet** (Phase 2).

## 6. Remaining backend tasks (Niharika)

Not implemented in Phase 1, by design:

1. **Transfers** (karigar → karigar, partial, job split): add `transfer` + `transfer_acknowledged` to `MaterialEventType` and `transfer` to `MOVEMENT_EVENTS`; from/to = karigar; check sender's balance with `ledger.lot_balances`; reuse the acknowledgement/reversal patterns in `services/custody.py`. Consider parent/child jobs (PRD "Metal Lineage Graph").
2. **Production tracking**: stage measurements (in/out gross, operator, scale) — likely a `measurement` table or `production_*` events that do not move custody; alloy additions change fineness (track gold and alloy separately, PRD §3).
3. **Returns**: finished goods / scrap / dust / WIP / partial returns as movement events karigar → vault with **gross, stone and net** separately, declared vs assayed fineness (assay evidence), retained scrap state.
4. **Reconciliation engine**: per-job bridge — issued fine = finished + returned scrap + retained scrap + closing WIP + documented loss + unexplained variance; configurable tolerance per job/contract (`loss_allowance_pct`, `contract_version`). Must be deterministic and drillable to event IDs.
5. **AI investigation**: read-only agent tools (`get_job_ledger`, `trace_lot`, `compare_measurements`, `calculate_balance`) over this API/DB; outputs separate verified facts / assumptions / missing evidence; never edits balances; manager resolution logged (`ReconciliationCase` table).
6. **Settlement**: versioned `SettlementRule` (labour model, loss allowance, effective dates), worksheet calculation, human approval workflow, audit.
7. **Deployment**: production config (`AURUM_ENV=production`, strong `AURUM_JWT_SECRET`, `AURUM_ALLOW_REGISTRATION=false`), managed Postgres, run `alembic upgrade head` on deploy, CI running pytest against PostgreSQL.

### Known limitations to keep in mind

- A reversed acknowledgement can't be re-signed (unique `(ref_event_id, event_type)`); reverse and re-issue instead. Relax deliberately if needed.
- Code generation (`K-0001`…) counts existing rows; concurrent creates may collide → 409 `duplicate_code` (retry). Fine for Phase 1 volumes.
- Access tokens only (no refresh tokens, no rate limiting, no password reset).
- `GET /karigars/hierarchy` computes holdings per karigar (N queries) — add an aggregate query if karigar counts grow large.
- Karigars do not log in yet; acknowledgements are recorded by vault staff with `acknowledgedByName` + `evidenceRef`.
