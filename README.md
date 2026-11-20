# AURUMTRACE

Precious-metal custody and manufacturing intelligence for jewellery manufacturers. AURUMTRACE tracks every gram of gold as it moves from the vault to head karigars, karigars and subcontractors and back. It reconciles what was issued against what was returned in fine-gold terms, and raises an exception for any variance beyond the agreed loss allowance.

## Live

| | Link |
|---|---|
| Frontend | https://aurumtrace-web-gamma.vercel.app |
| Backend API | https://aurumtrace-api-p1rr.onrender.com |
| API docs (Swagger) | https://aurumtrace-api-p1rr.onrender.com/docs |

The backend runs on Render's free tier, so the first request after it has been idle can take about 30 seconds.

## Features

- **Custody ledger:** issuance, full, partial and split transfers, and returns, each with a challan reference and receiver acknowledgement
- **Production tracking:** Alloying → Casting → Filing → Setting → Polishing → QC
- **Reconciliation:** fine gold = net metal × fineness, in `Decimal` to 0.001 g. Assayed fineness overrides declared fineness.
- **Exceptions and AI investigation:** custody timeline, linked evidence, explanation, then manager review
- **Settlement:** labour minus recovery for excess wastage, with an approval workflow
- **Append-only ledger:** database triggers block edits and deletes; corrections are made by reversal entries
- **Auth and roles:** JWT with bcrypt, and four roles: admin, manager, vault operator, viewer

## Stack

- **Frontend:** React 19, TypeScript, Vite, Three.js (React Three Fiber), GSAP, deployed on Vercel
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, deployed on Render
- **AI:** pluggable provider: deterministic by default, Gemini when configured

## Run locally

Frontend:

```bash
npm install
npm run dev
```

Backend: see [backend/README.md](backend/README.md) for setup, migrations and seed data.

## Tests

The backend has 105 automated tests in 17 files, covering:

- fine-gold maths
- issuance, transfers, production, returns, reconciliation and settlements
- auth and permissions
- the security audit
- the append-only ledger
- end-to-end workflows

```bash
cd backend
python -m pytest
```

## Docs

- [backend/docs/API.md](backend/docs/API.md): API reference
- [backend/docs/DEPLOYMENT.md](backend/docs/DEPLOYMENT.md): deployment
- [AURUMTRACE_FINAL_SIGNOFF_REPORT.md](AURUMTRACE_FINAL_SIGNOFF_REPORT.md): audit and test report
- [CONTRIBUTING.md](CONTRIBUTING.md): Git workflow

All data in the app is synthetic demo data.
