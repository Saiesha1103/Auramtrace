# Release handoff: agentic AI, karigar portal, two-party settlement

**For:** Niharika (backend & deployment)
**Branch:** `feat/landing-page` (commit `0afcfee` plus the follow-up that added this file)
**Code status:** done. 117/117 backend tests pass on SQLite, the frontend builds, and the main flows were checked in a browser against a local seeded database.
**Not yet verified:** PostgreSQL migration, live Gemini calls, deployment. Those are the steps below.

---

## What changed for operations

| Area | Change | Ops impact |
|---|---|---|
| Database | Migration `0003_agents_portal`: `users.karigar_id`, `job_orders.occasion_date/label`, settlement response/payment columns, new `agent_runs` table | Additive only: every new column is nullable, and nothing in `material_events` / `audit_events` is touched. The Docker entrypoint runs `alembic upgrade head` on start. |
| Dependencies | `httpx` moved from `requirements-dev.txt` to `requirements.txt` | Rebuild the image. Without it the Gemini path cannot run in production. |
| Config | New optional `AURUM_AI_PROVIDER`, `AURUM_GEMINI_API_KEY`, `AURUM_GEMINI_MODEL` | See step 3 |
| API | New `/api/v1/agents/*`, `/api/v1/portal/*`, `POST /settlements/worksheets/{id}/mark-paid`, `GET /karigars/{id}/track-record` | New `karigar` role. Karigar tokens get **403 on every staff endpoint** (deny-by-default in `deps.get_current_user`). |
| Behaviour | Jeweller approval no longer settles a job; the karigar must accept from the portal | Expected. The demo story depends on it. |
| Seed | `python -m scripts.seed` now **tops up** an already-seeded demo org (karigar logins, occasion dates, first watcher run) instead of exiting | Safe to re-run; it never touches custody history |

---

## Steps

### 1. Back up the database
Take a Render Postgres snapshot (or `pg_dump -Fc`) before deploying. The migration is additive, but take the backup anyway.

### 2. Deploy the backend
- Push `feat/landing-page` and let Render rebuild the service from `backend/Dockerfile`.
- **If the Render service does not use the Dockerfile**, make sure the start command runs migrations first:
  `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Check the deploy log for:
  `Running upgrade 0002_phase2 -> 0003_agents_portal`
- If the migration fails, roll back with `alembic downgrade 0002_phase2` and send me the error. Downgrade has been tested on SQLite only.

### 3. Turn on Gemini (recommended for the demo)
In the Render environment, add:
```
AURUM_AI_PROVIDER=gemini
AURUM_GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>   # add as a secret
AURUM_GEMINI_MODEL=gemini-2.5-flash
```
The free tier is enough. Without a key, the agents still work with the rule-based planner.

### 4. Top up the demo data
From the Render shell, in `/app`:
```
python -m scripts.seed
```
Expected output: `... was already seeded; topped up: karigar login mahesh@..., karigar login farida@..., occasion date on J-1190, occasion date on J-1186, first watcher agent run`

The demo password comes from `AURUM_DEMO_PASSWORD`, or the default in `scripts/seed.py`. Set `AURUM_DEMO_PASSWORD` first if the live demo must not use the default.

### 5. Deploy the frontend
Vercel rebuilds from the same push. `VITE_API_BASE_URL` already defaults to the Render URL, so no env change is needed.

### 6. Smoke test (about 5 minutes)
Use a manager login on the live site:
1. **AI Agents → Run watcher agent.** Expect critical alerts for J-1190 (Desai wedding) and draft messages. The `Planner` line should read `gemini_gemini-2.5-flash`. If it reads `rule_planner_v1 (gemini_fallback)`, the key or network is wrong; check the logs for `LLM watcher agent failed`.
2. **AI Agents → Investigation agent → Investigate** any case. The step trace should list several tool calls.
3. Sign out, then sign in as `mahesh@aurumtrace-demo.example.com`. Only the portal should load. Accept SW-0001.
4. Sign back in as manager. **AI Agents → Karigar payments → Record payment** on SW-0001.
5. Isolation check with Mahesh's token: `GET /api/v1/jobs` must return **403**.

Optional CLI check against PostgreSQL (needs a throwaway test DB):
```
AURUM_TEST_DATABASE_URL=postgresql+psycopg://.../aurumtrace_test python -m pytest
```

---

## Known limits (no deploy action needed)
- The "New job" form in the UI is still browser-only, so occasion dates are set through the API or the seed.
- Agents draft messages but do not send them; there is no WhatsApp integration by design.
- There is no refiner workflow yet. Scrap and dust returns are tracked, but sending them to a refiner and getting fine gold back is not.
