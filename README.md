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
- **Agentic AI (read-only, human-in-the-loop):**
  - *Investigation agent:* plans its own steps over 12 read-only tools (ledger, returns, assays, reconciliation, karigar custody), cites the record behind every fact, and drops any claim citing a record it never read
  - *Deadline & payment watcher:* flags jobs at risk against due dates and the customer's occasion date (wedding, engagement), and karigars waiting to be paid, then drafts WhatsApp messages for a person to review. It never sends anything.
  - Every tool call is saved as a trace and shown in the UI. Agents cannot move gold, approve settlements or send messages. Gemini function calling is used when configured; otherwise a deterministic planner runs the same loop.
- **Karigar portal:** each karigar signs in to see their own gold ledger, jobs, settlements and track record, and confirms receipt of gold issued to them. Karigar logins are denied every organisation-wide endpoint.
- **Two-party settlement:** draft → submitted → approved by the jeweller (four-eyes) → **accepted or disputed by the karigar** → paid. A job is settled only when the karigar accepts, and payment can be recorded only after that.
- **Karigar track record:** on-time delivery, occasion dates kept, wastage within allowance, disputes and average days to payment, all derived from the ledger rather than self-reported
- **Append-only ledger:** database triggers block edits and deletes; corrections are made by reversal entries
- **Auth and roles:** JWT with bcrypt; staff roles admin, manager, vault operator, viewer, plus a `karigar` self-service role

## Stack

- **Frontend:** React 19, TypeScript, Vite, Three.js (React Three Fiber), GSAP, deployed on Vercel
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, deployed on Render
- **AI:** a bounded tool-calling agent runtime (`backend/app/services/agent_runtime.py`). It uses Gemini function calling when `AURUM_AI_PROVIDER=gemini` and `AURUM_GEMINI_API_KEY` are set, and otherwise a deterministic rule-based planner. If the LLM fails, it falls back to that planner automatically.

## Run locally

Frontend:

```bash
npm install
npm run dev
```

Backend: see [backend/README.md](backend/README.md) for setup, migrations and seed data.

## Tests

The backend has 117 automated tests in 18 files, covering:

- fine-gold maths
- issuance, transfers, production, returns, reconciliation and settlements
- the agent loop (tool validation, organisation isolation, grounding, step limit, LLM fallback, Gemini wire format), the watcher agent, the karigar portal and two-party settlement
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
