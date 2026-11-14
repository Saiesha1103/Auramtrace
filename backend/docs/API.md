# AURUMTRACE API — Phase 1 reference

Base URL `http://localhost:8000` · all resource routes are under **`/api/v1`** · interactive docs at **`/docs`** (Swagger) and `/redoc` · schema at `/openapi.json`.

> Every example below was captured from the running application (synthetic data); UUIDs and timestamps will differ on your machine.

## Conventions (frontend contract)

| Topic | Rule |
|---|---|
| Field names | camelCase in JSON (snake_case is also accepted on input) |
| IDs | UUID strings. Human codes (`K-0001`, `J-0001`, `L-0001`) are separate `code` fields, unique per organisation; you may supply your own code on create |
| Weights | JSON numbers in **grams**, at most **3 decimals** (more is rejected, never rounded). `grossWeightG`, `netWeightG` (metal only), `stoneWeightG = gross − net`, `fineGoldG` |
| Fineness | **parts per thousand** (`916.0` = 22K, `995.0` bar), at most 1 decimal. Frontend currently stores 0.916 → multiply by 1000 |
| Fine gold | `netWeightG × finenessPpt ÷ 1000`, rounded half-up to 0.001 g. Balances are summed in net metal per lot, then converted (no rounding drift across partial issues) |
| Timestamps | ISO-8601 UTC with `Z` (`2026-11-12T10:42:00.123456Z`); `dueDate` is `YYYY-MM-DD`. `occurredAt` (business time, optional on writes) vs `recordedAt` (server time) |
| Lists | `{"items": [...], "total", "limit", "offset"}`; `limit` ≤ 200 (events ≤ 500) |
| Auth | `Authorization: Bearer <accessToken>`; tokens expire after `expiresIn` seconds (default 3600) |
| Errors | always `{"error": {"code", "message", "details"}}` — see [Errors](#errors) |

### Enums

| Enum | Values |
|---|---|
| `UserRole` | `admin`, `manager`, `vault_operator`, `viewer` |
| `KarigarKind` | `head_karigar`, `karigar`, `subcontractor` |
| `KarigarStatus` | `active`, `inactive` |
| `JobStatus` | `draft`, `issued`, `in_production`, `returned`, `reconciled`, `settled`, `cancelled` — Phase 1 sets `draft` → `issued` (first issue) and `cancelled`; the rest are reserved for later phases |
| `Karat` | `24K` (995), `22K` (916), `18K` (750), `14K` (585) — default `targetFinenessPpt` |
| `MaterialEventType` | `lot_received`, `issue`, `issue_acknowledged`, `reversal` |
| `CustodianType` | `external`, `vault`, `karigar` |
| `MeasurementMethod` | `manual`, `imported`, `device` |

Frontend mapping (current `src/app/data/types.ts`): role labels `Head karigar` → `head_karigar`; job status `In production` → `in_production`; fineness `0.995` → `995.0`.

### Permission matrix

| Action | admin | manager | vault_operator | viewer |
|---|:-:|:-:|:-:|:-:|
| Read anything in own organisation | ✓ | ✓ | ✓ | ✓ |
| Create / edit karigars, jobs | ✓ | ✓ | | |
| Receive lots, issue, record acknowledgement | ✓ | ✓ | ✓ | |
| Reverse events (corrections) | ✓ | ✓ | | |
| List users, read audit trail | ✓ | ✓ | | |
| Create / edit users, rename organisation | ✓ | | | |

Every query is scoped to the caller's organisation; another organisation's records return **404**.

## Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/register` | public (dev) | Create organisation + first admin (disabled when `AURUM_ALLOW_REGISTRATION=false`) |
| POST | `/api/v1/auth/login` | public | Email + password → bearer token |
| GET | `/api/v1/auth/me` | any | Current user |
| GET / PATCH | `/api/v1/organisations/me` | any / admin | View / rename organisation |
| GET / POST | `/api/v1/users` | admin+manager / admin | List / add users |
| PATCH | `/api/v1/users/{id}` | admin | Change name, role, active flag (cannot lock yourself out) |
| GET | `/api/v1/audit` | admin, manager | Audit trail (filters `entityType`, `entityId`) |
| GET / POST | `/api/v1/karigars` | any / manage | Directory (`kind`, `status`, `headKarigarId`, `q`) / register |
| GET | `/api/v1/karigars/hierarchy` | any | Head karigars → teams, independents; fine gold held |
| GET / PATCH | `/api/v1/karigars/{id}` | any / manage | Profile with derived custody / edit fields & status |
| GET / POST | `/api/v1/jobs` | any / manage | List (`status`, `headKarigarId`, `q`) / create |
| GET / PATCH | `/api/v1/jobs/{id}` | any / manage | Detail (issued totals, custody, events) / edit or cancel |
| GET / POST | `/api/v1/lots` | any / vault ops | List with balances / receive a lot (appends `lot_received`) |
| GET | `/api/v1/lots/{id}` | any | Lot with vault / with-karigars balances |
| POST | `/api/v1/lots/{id}/issue` | vault ops | Issue to a karigar against a job (appends `issue`) |
| GET | `/api/v1/events` | any | History (`lotId`, `jobId`, `karigarId`, `eventType`, `from`, `to`) |
| GET | `/api/v1/events/{id}` | any | One event + derived `state` |
| POST | `/api/v1/events/{id}/acknowledge` | vault ops | Receiver signs for an issue (appends `issue_acknowledged`) |
| POST | `/api/v1/events/{id}/reverse` | manage | Correction (appends `reversal`) |
| POST | `/api/v1/transfers` | manage, vault ops | Transfer gold custody between eligible karigars |
| GET | `/api/v1/transfers` | any | List material transfers with filtering |
| GET | `/api/v1/transfers/{id}` | any | Transfer details and acknowledgement state |
| POST | `/api/v1/transfers/{id}/acknowledge` | any (receiver) | Acknowledge receipt of transferred material |
| POST | `/api/v1/transfers/{id}/reverse` | manage | Reversal of a transfer via compensating event |
| POST | `/api/v1/jobs/{id}/split` | manage | Divide a job into sub-orders across karigars |
| GET | `/api/v1/jobs/{id}/lineage` | any | Tree of parent-child job lineage relationships |
| GET | `/api/v1/jobs/{id}/custody-lineage` | any | Complete custody lineage movement DAG |
| POST | `/api/v1/production/entries` | manage, vault ops | Create manufacturing stage work entry |
| GET | `/api/v1/production/entries` | any | List production stage entries |
| GET / PATCH | `/api/v1/production/entries/{id}` | any / manage | View entry / update permissible metadata |
| POST | `/api/v1/production/entries/{id}/complete` | manage, vault ops | Record completion of a manufacturing stage |
| POST | `/api/v1/production/measurements` | manage, vault ops | Record scale weights at a production stage |
| GET | `/api/v1/production/measurements` | any | List production physical measurements |
| GET | `/api/v1/production/jobs/{jobId}/timeline` | any | Chronological stage timeline for a job |
| POST | `/api/v1/returns` | manage, vault ops | Return finished jewellery, scrap, dust, or WIP |
| GET | `/api/v1/returns` | any | List material returns |
| GET | `/api/v1/returns/{id}` | any | Return details and associated material event |
| POST | `/api/v1/returns/{id}/assay` | manage, vault ops | Record verified fire assay result on a return |
| POST | `/api/v1/jobs/{id}/reconcile` | manage | Deterministic fine-gold reconciliation run |
| GET | `/api/v1/jobs/{id}/reconciliation` | any | Latest fine-gold reconciliation snapshot |
| GET | `/api/v1/reconciliations` | any | List historical reconciliation snapshots |
| GET | `/api/v1/reconciliations/summary` | any | Organisation-wide variance & reconciliation metrics |
| GET | `/api/v1/reconciliations/compare` | any | Side-by-side delta between two reconciliation runs |
| GET | `/api/v1/reconciliations/{id}` | any | Drill-down into reconciliation line items |
| POST | `/api/v1/exceptions/detect` | manage | Automated anomaly, purity, and variance scan |
| GET | `/api/v1/exceptions` | any | List exception cases |
| GET | `/api/v1/exceptions/{id}` | any | Exception case details and timeline |
| PATCH | `/api/v1/exceptions/{id}/assign` | manage | Assign investigator to exception case |
| PATCH | `/api/v1/exceptions/{id}/status` | manage | Update exception case status |
| POST | `/api/v1/exceptions/{id}/notes` | manage | Append investigation notes to case |
| POST / GET | `/api/v1/exceptions/{id}/evidence` | manage / any | Attach evidence document / list evidence |
| POST | `/api/v1/exceptions/{id}/resolve` | manage | Resolve exception with documented rationale |
| POST | `/api/v1/exceptions/{id}/dismiss` | manage | Dismiss exception with mandatory justification |
| POST | `/api/v1/investigations/run` | manage | Run AI investigation assistant on an exception |
| GET | `/api/v1/investigations` | any | List historical AI investigation runs |
| GET | `/api/v1/investigations/{id}` | any | View AI investigation report & grounded facts |
| GET | `/api/v1/investigations/tools/*` | any | 12 strictly read-only inspection tools |
| POST | `/api/v1/settlements/rules` | admin, manager | Create commercial karigar settlement rule |
| GET | `/api/v1/settlements/rules` | any | List commercial settlement rules |
| GET | `/api/v1/settlements/rules/{id}` | any | Retrieve specific settlement rule |
| POST | `/api/v1/settlements/worksheets` | manage | Generate commercial settlement worksheet |
| GET | `/api/v1/settlements/worksheets` | any | List commercial settlement worksheets |
| GET | `/api/v1/settlements/worksheets/{id}` | any | View settlement worksheet and financial breakdown |
| POST | `/api/v1/settlements/worksheets/{id}/submit` | manage | Submit worksheet for director approval |
| POST | `/api/v1/settlements/worksheets/{id}/approve` | admin, manager | Authorize settlement & treasury disbursement |
| POST | `/api/v1/settlements/worksheets/{id}/reject` | admin, manager | Reject worksheet back to draft |
| GET | `/health` | public | Liveness |

There are **no** PUT/PATCH/DELETE routes for events — they return `405`.

## Auth

`POST /api/v1/auth/register` → **201**

Request

```json
{
  "organisationName": "Demo Jewellers",
  "fullName": "Asha Admin",
  "email": "asha@example.com",
  "password": "Example-Pass-2026"
}
```

Response

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5…",
  "tokenType": "bearer",
  "expiresIn": 3600,
  "user": {
    "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
    "organisationId": "e2620156-3bd7-42c8-9ed9-b64271aa86d7",
    "email": "asha@example.com",
    "fullName": "Asha Admin",
    "role": "admin",
    "isActive": true,
    "createdAt": "2026-11-12T12:51:47.101307Z"
  }
}
```

`POST /api/v1/auth/login` → **200**

Request

```json
{
  "email": "asha@example.com",
  "password": "Example-Pass-2026"
}
```

Response

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5…",
  "tokenType": "bearer",
  "expiresIn": 3600,
  "user": {
    "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
    "organisationId": "e2620156-3bd7-42c8-9ed9-b64271aa86d7",
    "email": "asha@example.com",
    "fullName": "Asha Admin",
    "role": "admin",
    "isActive": true,
    "createdAt": "2026-11-12T12:51:47.101307Z"
  }
}
```

## Karigars

`POST /api/v1/karigars` → **201** — omit `code` to get `K-0001`, `K-0002`, …

Request

```json
{
  "code": "K-02",
  "name": "Farida Shaikh",
  "kind": "head_karigar",
  "unit": "Unit B · Kalbadevi",
  "skills": [
    "Temple work"
  ]
}
```

Response

```json
{
  "id": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "code": "K-02",
  "name": "Farida Shaikh",
  "kind": "head_karigar",
  "headKarigarId": null,
  "unit": "Unit B · Kalbadevi",
  "contact": null,
  "skills": [
    "Temple work"
  ],
  "status": "active",
  "createdAt": "2026-11-12T12:51:47.882260Z"
}
```

`GET /api/v1/karigars/hierarchy` → **200**

Response

```json
[
  {
    "id": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
    "code": "K-02",
    "name": "Farida Shaikh",
    "kind": "head_karigar",
    "status": "active",
    "fineGoldHeldG": 19.9,
    "children": [
      {
        "id": "12db0ae7-6ced-4420-bb5c-0826d170f021",
        "code": "K-07",
        "name": "Anil Verma",
        "kind": "karigar",
        "status": "active",
        "fineGoldHeldG": 0.0,
        "children": []
      }
    ]
  }
]
```

`GET /api/v1/karigars/c3dfbfb2-b68e-4923-8899-916f4ae4565d` → **200** — custody is derived from events

Response

```json
{
  "id": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "code": "K-02",
  "name": "Farida Shaikh",
  "kind": "head_karigar",
  "headKarigarId": null,
  "unit": "Unit B · Kalbadevi",
  "contact": null,
  "skills": [
    "Temple work"
  ],
  "status": "active",
  "createdAt": "2026-11-12T12:51:47.882260Z",
  "headKarigar": null,
  "team": [
    {
      "id": "12db0ae7-6ced-4420-bb5c-0826d170f021",
      "code": "K-07",
      "name": "Anil Verma",
      "kind": "karigar"
    }
  ],
  "custody": {
    "fineGoldG": 19.9,
    "netWeightG": 20.0,
    "grossWeightG": 20.0,
    "pendingAcknowledgements": 0,
    "byJob": [
      {
        "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
        "jobCode": "J-1182",
        "fineGoldG": 19.9,
        "netWeightG": 20.0
      }
    ]
  },
  "recentEvents": [
    "… 2 events (EventOut)"
  ]
}
```

## Jobs

`POST /api/v1/jobs` → **201**

Request

```json
{
  "code": "J-1182",
  "title": "Temple bangles",
  "karat": "22K",
  "pieces": 6,
  "targetGrossPerPieceG": 5.2,
  "lossAllowancePct": 1.2,
  "headKarigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "dueDate": "2026-11-12",
  "contractVersion": "KC-2026.1"
}
```

Response

```json
{
  "id": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "code": "J-1182",
  "title": "Temple bangles",
  "orderRef": null,
  "process": null,
  "karat": "22K",
  "targetFinenessPpt": 916.0,
  "pieces": 6,
  "targetGrossPerPieceG": 5.2,
  "lossAllowancePct": "1.2",
  "contractVersion": "KC-2026.1",
  "headKarigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "dueDate": "2026-11-12",
  "notes": null,
  "status": "draft",
  "createdAt": "2026-11-12T12:51:48.006701Z"
}
```

`GET /api/v1/jobs/44fe79e3-f86b-474d-8d05-9a04a035cab5` → **200**

Response

```json
{
  "id": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "code": "J-1182",
  "title": "Temple bangles",
  "orderRef": null,
  "process": null,
  "karat": "22K",
  "targetFinenessPpt": 916.0,
  "pieces": 6,
  "targetGrossPerPieceG": 5.2,
  "lossAllowancePct": "1.2",
  "contractVersion": "KC-2026.1",
  "headKarigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "dueDate": "2026-11-12",
  "notes": null,
  "status": "issued",
  "createdAt": "2026-11-12T12:51:48.006701Z",
  "issued": {
    "grossWeightG": 20.0,
    "netWeightG": 20.0,
    "fineGoldG": 19.9
  },
  "pendingAcknowledgements": 0,
  "custody": [
    {
      "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
      "karigarCode": "K-02",
      "karigarName": "Farida Shaikh",
      "fineGoldG": 19.9,
      "netWeightG": 20.0
    }
  ],
  "events": [
    {
      "id": "55ba8f2a-1d9e-46c0-954e-402d0d493913",
      "eventType": "issue",
      "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
      "lotCode": "L-3301",
      "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
      "jobCode": "J-1182",
      "from": {
        "type": "vault",
        "karigarId": null,
        "karigarCode": null,
        "karigarName": null
      },
      "to": {
        "type": "karigar",
        "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
        "karigarCode": "K-02",
        "karigarName": "Farida Shaikh"
      },
      "grossWeightG": 20.0,
      "netWeightG": 20.0,
      "finenessPpt": 995.0,
      "fineGoldG": 19.9,
      "measurement": {
        "scaleId": "SC-01",
        "operatorName": "Vault desk",
        "method": "manual"
      },
      "challanRef": "JWC-26-3301",
      "evidenceRef": null,
      "note": null,
      "refEventId": null,
      "acknowledgedByName": null,
      "occurredAt": "2026-11-12T12:51:48.123813Z",
      "recordedAt": "2026-11-12T12:51:48.123819Z",
      "recordedBy": {
        "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
        "fullName": "Asha Admin"
      },
      "state": {
        "reversed": false,
        "reversalEventId": null,
        "acknowledged": true,
        "acknowledgementEventId": "567b3faf-998a-4d14-b331-f86d89b462f9"
      }
    },
    "… 3 more events"
  ]
}
```

## Gold lots & issuance

`POST /api/v1/lots` → **201** — gross, net and fineness recorded separately; appends a `lot_received` event

Request

```json
{
  "code": "L-3301",
  "source": "Bar 995 · B-792",
  "grossWeightG": 30.151,
  "netWeightG": 30.151,
  "finenessPpt": 995,
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault desk",
    "method": "manual"
  },
  "challanRef": "RCPT-778"
}
```

Response

```json
{
  "id": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
  "code": "L-3301",
  "metalType": "gold",
  "source": "Bar 995 · B-792",
  "grossWeightG": 30.151,
  "netWeightG": 30.151,
  "stoneWeightG": 0.0,
  "finenessPpt": 995.0,
  "fineGoldG": 30.0,
  "sourceJobId": null,
  "createdAt": "2026-11-12T12:51:48.065114Z",
  "balance": {
    "vault": {
      "grossWeightG": 30.151,
      "netWeightG": 30.151,
      "fineGoldG": 30.0
    },
    "withKarigars": {
      "grossWeightG": 0.0,
      "netWeightG": 0.0,
      "fineGoldG": 0.0
    }
  }
}
```

`POST /api/v1/lots/7e2a037b-a44d-49db-8396-f3b7c2be64d0/issue` → **201** — pending acknowledgement until the receiver signs

Request

```json
{
  "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "grossWeightG": 20.0,
  "netWeightG": 20.0,
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault desk",
    "method": "manual"
  },
  "challanRef": "JWC-26-3301"
}
```

Response

```json
{
  "id": "55ba8f2a-1d9e-46c0-954e-402d0d493913",
  "eventType": "issue",
  "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
  "lotCode": "L-3301",
  "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "jobCode": "J-1182",
  "from": {
    "type": "vault",
    "karigarId": null,
    "karigarCode": null,
    "karigarName": null
  },
  "to": {
    "type": "karigar",
    "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
    "karigarCode": "K-02",
    "karigarName": "Farida Shaikh"
  },
  "grossWeightG": 20.0,
  "netWeightG": 20.0,
  "finenessPpt": 995.0,
  "fineGoldG": 19.9,
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault desk",
    "method": "manual"
  },
  "challanRef": "JWC-26-3301",
  "evidenceRef": null,
  "note": null,
  "refEventId": null,
  "acknowledgedByName": null,
  "occurredAt": "2026-11-12T12:51:48.123813Z",
  "recordedAt": "2026-11-12T12:51:48.123819Z",
  "recordedBy": {
    "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
    "fullName": "Asha Admin"
  },
  "state": {
    "reversed": false,
    "reversalEventId": null,
    "acknowledged": false,
    "acknowledgementEventId": null
  }
}
```

`GET /api/v1/lots/7e2a037b-a44d-49db-8396-f3b7c2be64d0` → **200** — balances after a 20 g issue and a reversed 2 g issue

Response

```json
{
  "id": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
  "code": "L-3301",
  "metalType": "gold",
  "source": "Bar 995 · B-792",
  "grossWeightG": 30.151,
  "netWeightG": 30.151,
  "stoneWeightG": 0.0,
  "finenessPpt": 995.0,
  "fineGoldG": 30.0,
  "sourceJobId": null,
  "createdAt": "2026-11-12T12:51:48.065114Z",
  "balance": {
    "vault": {
      "grossWeightG": 10.151,
      "netWeightG": 10.151,
      "fineGoldG": 10.1
    },
    "withKarigars": {
      "grossWeightG": 20.0,
      "netWeightG": 20.0,
      "fineGoldG": 19.9
    }
  }
}
```

## Acknowledgement & corrections

`POST /api/v1/events/55ba8f2a-1d9e-46c0-954e-402d0d493913/acknowledge` → **201**

Request

```json
{
  "acknowledgedByName": "Farida Shaikh",
  "evidenceRef": "ACK-3301 signed slip"
}
```

Response

```json
{
  "id": "567b3faf-998a-4d14-b331-f86d89b462f9",
  "eventType": "issue_acknowledged",
  "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
  "lotCode": "L-3301",
  "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "jobCode": "J-1182",
  "from": {
    "type": null,
    "karigarId": null,
    "karigarCode": null,
    "karigarName": null
  },
  "to": {
    "type": "karigar",
    "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
    "karigarCode": "K-02",
    "karigarName": "Farida Shaikh"
  },
  "grossWeightG": null,
  "netWeightG": null,
  "finenessPpt": null,
  "fineGoldG": null,
  "measurement": null,
  "challanRef": null,
  "evidenceRef": "ACK-3301 signed slip",
  "note": null,
  "refEventId": "55ba8f2a-1d9e-46c0-954e-402d0d493913",
  "acknowledgedByName": "Farida Shaikh",
  "occurredAt": "2026-11-12T12:51:48.247372Z",
  "recordedAt": "2026-11-12T12:51:48.247377Z",
  "recordedBy": {
    "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
    "fullName": "Asha Admin"
  },
  "state": {
    "reversed": false,
    "reversalEventId": null,
    "acknowledged": null,
    "acknowledgementEventId": null
  }
}
```

`POST /api/v1/events/53c506b2-5195-4a22-a65e-9749e1c8a926/reverse` → **201** — mirror image of the original; the original row is untouched and now reports `state.reversed = true`

Request

```json
{
  "reason": "Issued to the wrong karigar; re-issuing to K-02"
}
```

Response

```json
{
  "id": "6d12ae88-3922-49f3-9e61-5992bad8541b",
  "eventType": "reversal",
  "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
  "lotCode": "L-3301",
  "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "jobCode": "J-1182",
  "from": {
    "type": "karigar",
    "karigarId": "12db0ae7-6ced-4420-bb5c-0826d170f021",
    "karigarCode": "K-07",
    "karigarName": "Anil Verma"
  },
  "to": {
    "type": "vault",
    "karigarId": null,
    "karigarCode": null,
    "karigarName": null
  },
  "grossWeightG": 2.0,
  "netWeightG": 2.0,
  "finenessPpt": 995.0,
  "fineGoldG": 1.99,
  "measurement": null,
  "challanRef": null,
  "evidenceRef": null,
  "note": "Issued to the wrong karigar; re-issuing to K-02",
  "refEventId": "53c506b2-5195-4a22-a65e-9749e1c8a926",
  "acknowledgedByName": null,
  "occurredAt": "2026-11-12T12:51:48.372202Z",
  "recordedAt": "2026-11-12T12:51:48.372209Z",
  "recordedBy": {
    "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
    "fullName": "Asha Admin"
  },
  "state": {
    "reversed": false,
    "reversalEventId": null,
    "acknowledged": null,
    "acknowledgementEventId": null
  }
}
```

Reversal rules: a reversal can't be reversed (`not_reversible`); an event is reversed at most once (`already_reversed`); an acknowledged issue needs its acknowledgement reversed first (`acknowledged_issue`); a receipt can't be reversed while metal from the lot is issued out (`lot_in_use`). A reversed acknowledgement cannot be re-signed in Phase 1 — reverse and re-issue instead.

## Event history

`GET /api/v1/events?jobId=44fe79e3-f86b-474d-8d05-9a04a035cab5&eventType=issue&limit=1` → **200**

Response

```json
{
  "items": [
    {
      "id": "55ba8f2a-1d9e-46c0-954e-402d0d493913",
      "eventType": "issue",
      "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
      "lotCode": "L-3301",
      "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
      "jobCode": "J-1182",
      "from": {
        "type": "vault",
        "karigarId": null,
        "karigarCode": null,
        "karigarName": null
      },
      "to": {
        "type": "karigar",
        "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
        "karigarCode": "K-02",
        "karigarName": "Farida Shaikh"
      },
      "grossWeightG": 20.0,
      "netWeightG": 20.0,
      "finenessPpt": 995.0,
      "fineGoldG": 19.9,
      "measurement": {
        "scaleId": "SC-01",
        "operatorName": "Vault desk",
        "method": "manual"
      },
      "challanRef": "JWC-26-3301",
      "evidenceRef": null,
      "note": null,
      "refEventId": null,
      "acknowledgedByName": null,
      "occurredAt": "2026-11-12T12:51:48.123813Z",
      "recordedAt": "2026-11-12T12:51:48.123819Z",
      "recordedBy": {
        "id": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
        "fullName": "Asha Admin"
      },
      "state": {
        "reversed": false,
        "reversalEventId": null,
        "acknowledged": true,
        "acknowledgementEventId": "567b3faf-998a-4d14-b331-f86d89b462f9"
      }
    }
  ],
  "total": 2,
  "limit": 1,
  "offset": 0
}
```

## Audit

`GET /api/v1/audit?limit=2` → **200**

Response

```json
{
  "items": [
    {
      "id": "fd55121a-6e23-4963-b380-477a44cd38ab",
      "actorUserId": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
      "actorName": "Asha Admin",
      "action": "material.reversed",
      "entityType": "material_event",
      "entityId": "6d12ae88-3922-49f3-9e61-5992bad8541b",
      "details": {
        "reversedEventId": "53c506b2-5195-4a22-a65e-9749e1c8a926",
        "reversedEventType": "issue",
        "reason": "Issued to the wrong karigar; re-issuing to K-02"
      },
      "createdAt": "2026-11-12T12:51:48.381122Z"
    },
    {
      "id": "a83ad888-ef28-47e9-ab80-5e62d4402658",
      "actorUserId": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
      "actorName": "Asha Admin",
      "action": "material.issued",
      "entityType": "material_event",
      "entityId": "53c506b2-5195-4a22-a65e-9749e1c8a926",
      "details": {
        "lot": "L-3301",
        "job": "J-1182",
        "karigar": "K-07",
        "netWeightG": "2.000",
        "fineGoldG": "1.990",
        "challanRef": null
      },
      "createdAt": "2026-11-12T12:51:48.323529Z"
    }
  ],
  "total": 9,
  "limit": 2,
  "offset": 0
}
```

## Errors

| HTTP | `error.code` examples | When |
|---|---|---|
| 401 | `unauthorized`, `invalid_token`, `invalid_credentials`, `account_inactive` | missing/expired token, bad login |
| 403 | `forbidden` (`details.requiredRoles`), `registration_disabled` | role not allowed |
| 404 | `not_found` | missing, or in another organisation |
| 405 | `method_not_allowed` | e.g. `DELETE /events/{id}` |
| 409 | `email_taken`, `duplicate_code`, `already_acknowledged`, `already_reversed`, `append_only_violation`, `conflict` | duplicates / history protection |
| 422 | `validation_error` (`details[]` with `field`, `message`), `insufficient_balance`, `karigar_inactive`, `job_cancelled`, `job_has_custody`, `invalid_hierarchy`, `has_active_team`, `event_reversed`, `not_acknowledgeable`, `not_reversible`, `acknowledged_issue`, `lot_in_use`, `self_lockout` | bad input or custody rule |

`POST /api/v1/lots` → **422**

Request

```json
{
  "grossWeightG": 10.0001,
  "netWeightG": 12,
  "finenessPpt": 1200,
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault desk",
    "method": "manual"
  }
}
```

Response

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {
        "field": "grossWeightG",
        "message": "Value error, Weights are recorded to 0.001 g; use at most 3 decimal places",
        "type": "value_error"
      },
      {
        "field": "finenessPpt",
        "message": "Value error, Fineness must be greater than 0 and at most 999.9 parts per thousand",
        "type": "value_error"
      }
    ]
  }
}
```

`POST /api/v1/lots/7e2a037b-a44d-49db-8396-f3b7c2be64d0/issue` → **422**

Request

```json
{
  "jobId": "44fe79e3-f86b-474d-8d05-9a04a035cab5",
  "karigarId": "c3dfbfb2-b68e-4923-8899-916f4ae4565d",
  "grossWeightG": 50.0,
  "netWeightG": 50.0,
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault desk",
    "method": "manual"
  }
}
```

Response

```json
{
  "error": {
    "code": "insufficient_balance",
    "message": "Lot L-3301 has only 10.151 g net / 10.151 g gross in the vault",
    "details": {
      "lotId": "7e2a037b-a44d-49db-8396-f3b7c2be64d0",
      "availableNetWeightG": 10.151,
      "availableGrossWeightG": 10.151,
      "requestedNetWeightG": 50.0
    }
  }
}
```

`POST /api/v1/events/55ba8f2a-1d9e-46c0-954e-402d0d493913/acknowledge` → **409**

Request

```json
{
  "acknowledgedByName": "Farida Shaikh"
}
```

Response

```json
{
  "error": {
    "code": "already_acknowledged",
    "message": "This issue is already acknowledged",
    "details": null
  }
}
```

`GET /api/v1/jobs` → **401**

Response

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Authentication required",
    "details": null
  }
}
```

---

# Phase 2 Endpoints Reference

---

## 1. Material Transfers & Job Splitting

### Create Transfer
`POST /api/v1/transfers` → **201 Created**  
**Role:** `admin`, `manager`, `vault_operator`

Transfers gold custody between eligible karigars. Checks that the sender holds sufficient available net metal from the specified lot. Uses row-level locking on `material_lots` to prevent concurrent overspending.

Request:
```json
{
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "fromKarigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "toKarigarId": "23a1ef50-48e0-47fa-80df-116110996841",
  "lotId": "64e3a89d-f2bb-4d63-91ce-e07055ac35c0",
  "grossWeightG": 15.000,
  "netWeightG": 15.000,
  "challanRef": "CH-TR-001",
  "measurement": {
    "scaleId": "SC-01",
    "operatorName": "Vault Officer",
    "method": "manual"
  }
}
```

Response:
```json
{
  "id": "e441cbba-c90a-4fa0-826c-d2c6c06a3e01",
  "organisationId": "e2620156-3bd7-42c8-9ed9-b64271aa86d7",
  "eventType": "transfer",
  "lotId": "64e3a89d-f2bb-4d63-91ce-e07055ac35c0",
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "fromType": "karigar",
  "fromKarigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "toType": "karigar",
  "toKarigarId": "23a1ef50-48e0-47fa-80df-116110996841",
  "grossWeightG": 15.0,
  "netWeightG": 15.0,
  "finenessPpt": 916.0,
  "fineGoldG": 13.74,
  "scaleId": "SC-01",
  "operatorName": "Vault Officer",
  "measurementMethod": "manual",
  "challanRef": "CH-TR-001",
  "evidenceRef": null,
  "note": null,
  "recordedById": "2eeef155-0b4d-4b4a-ad76-00b8dcadf3a6",
  "occurredAt": "2026-11-13T10:00:00Z",
  "recordedAt": "2026-11-13T10:00:00.123456Z",
  "state": "pending"
}
```

### Acknowledge Transfer
`POST /api/v1/transfers/{id}/acknowledge` → **200 OK**  
**Role:** Any authenticated user in organization (typically receiving artisan)

Request:
```json
{
  "acknowledgedByName": "Ravi Kumar",
  "evidenceRef": "EVID-ACK-001"
}
```

### Reverse Transfer
`POST /api/v1/transfers/{id}/reverse` → **200 OK**  
**Role:** `admin`, `manager`

Appends an immutable compensating `reversal` event. The original transfer event remains forever in ledger history.

Request:
```json
{
  "reason": "Transfer entered in error; work reassigned to casting master.",
  "notes": "Compensating event appended"
}
```

### Split Job Order
`POST /api/v1/jobs/{id}/split` → **201 Created**  
**Role:** `admin`, `manager`

Divides a job order into sub-orders across karigars while maintaining immutable parent-child lineage.

Request:
```json
{
  "splits": [
    {
      "code": "J-1160-A",
      "title": "Jhumka Earring Body",
      "pieces": 6,
      "headKarigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf"
    },
    {
      "code": "J-1160-B",
      "title": "Jhumka Filigree Hangings",
      "pieces": 6,
      "headKarigarId": "23a1ef50-48e0-47fa-80df-116110996841"
    }
  ]
}
```

---

## 2. Production Process Tracking

### Create Production Entry
`POST /api/v1/production/entries` → **201 Created**  
**Role:** `admin`, `manager`, `vault_operator`

Request:
```json
{
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "karigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "stage": "Melting & Casting",
  "inputGrossWeightG": 20.000,
  "inputNetMetalWeightG": 20.000,
  "finenessPpt": 916.0,
  "notes": "Lost-wax investment casting"
}
```

### Record Production Measurement
`POST /api/v1/production/measurements` → **201 Created**  
**Role:** `admin`, `manager`, `vault_operator`

Records physical scale weights at a production stage. If a correction is needed, previous records remain marked as `isSuperseded: true`.

Request:
```json
{
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "karigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "stage": "Melting & Casting",
  "inputGrossWeightG": 20.000,
  "inputNetMetalWeightG": 20.000,
  "outputGrossWeightG": 19.820,
  "outputNetMetalWeightG": 19.820,
  "stoneWeightG": 0.000,
  "alloyWeightG": 0.000,
  "finenessPpt": 916.0,
  "pieces": 6,
  "notes": "Sprues separated and weighed"
}
```

### Complete Production Stage
`POST /api/v1/production/entries/{id}/complete` → **200 OK**  
**Role:** `admin`, `manager`, `vault_operator`

---

## 3. Material Returns & Assay Verification

### Create Return
`POST /api/v1/returns` → **201 Created**  
**Role:** `admin`, `manager`, `vault_operator`

Returns finished jewellery, scrap, dust, or intermediate WIP. Non-gold stones are strictly separated from net gold. Produces an immutable `return_vault` material event.

Request:
```json
{
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "karigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "lotId": "64e3a89d-f2bb-4d63-91ce-e07055ac35c0",
  "returnCategory": "finished_jewellery",
  "grossWeightG": 18.500,
  "netMetalWeightG": 16.500,
  "stoneWeightG": 2.000,
  "declaredFinenessPpt": 916.0,
  "pieces": 6,
  "isPartial": true,
  "retainedScrapG": 0.150,
  "challanRef": "RET-001",
  "measurement": {
    "scaleId": "SC-VAULT-01",
    "operatorName": "Vault Officer",
    "method": "device"
  }
}
```

Response:
```json
{
  "id": "a98dfb01-382a-4467-bcda-998811223344",
  "code": "RET-0001",
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "karigarId": "1b59fbde-2f13-4f3b-ace8-9d4fdd34a6cf",
  "lotId": "64e3a89d-f2bb-4d63-91ce-e07055ac35c0",
  "returnCategory": "finished_jewellery",
  "grossWeightG": 18.5,
  "netMetalWeightG": 16.5,
  "stoneWeightG": 2.0,
  "declaredFinenessPpt": 916.0,
  "assayedFinenessPpt": null,
  "fineGoldG": 15.114,
  "pieces": 6,
  "isPartial": true,
  "retainedScrapG": 0.15,
  "challanRef": "RET-001",
  "assayEvidenceRef": null,
  "notes": null,
  "createdAt": "2026-11-13T10:30:00Z"
}
```

### Record Assay Verification
`POST /api/v1/returns/{id}/assay` → **200 OK**  
**Role:** `admin`, `manager`, `vault_operator`

Updates verified fire assay purity and recalculates fine gold equivalent.

Request:
```json
{
  "assayedFinenessPpt": 912.0,
  "assayEvidenceRef": "CERT-ASSAY-8821",
  "notes": "Verified by National Hallmarking Laboratory"
}
```

---

## 4. Fine-Gold Reconciliation Engine

### Reconcile Job
`POST /api/v1/jobs/{id}/reconcile` → **201 Created**  
**Role:** `admin`, `manager`

Executes the deterministic fine-gold reconciliation equation:
$$\text{Issued Fine Gold} = \text{Finished Jewellery Fine} + \text{Returned Scrap Fine} + \text{Retained Scrap Fine} + \text{Closing WIP Fine} + \text{Documented Loss} + \text{Unexplained Variance}$$

### Dual Loss Allowance Architecture: Manufacturing vs. Commercial

AURUMTRACE strictly separates physical engineering tolerances from commercial contractual recovery rules:

| Attribute | Location | Governed By | Purpose | Authoritative For |
|---|---|---|---|---|
| **Shop-Floor Loss Allowance** | `JobOrder.loss_allowance_pct` | Production / Goldsmithing Engineering | Acceptable physical mass loss during casting, filing, and polishing | `ReconciliationRun.status` (`within_allowance` vs `above_allowance`) |
| **Commercial Wastage Allowance** | `SettlementRule.loss_allowance_pct` | Commercial Artisan Agreement | Maximum unrecovered fine gold absorbed by manufacturer before financial recovery | `SettlementWorksheet.wastage_allowance_fine_g` and excess recovery deductions |

*Why they differ:* A delicate bridal choker may have a physical workshop tolerance of `1.2%` due to intricate filigree loss, while the commercial agreement with the master artisan may grant a contractual wastage ceiling of `1.5%`. If actual loss is `0.595 g` against `36.640 g` issued:
- Reconciliation flags `above_allowance` because $0.595\text{ g} > 0.440\text{ g}$ ($1.2\%$).
- Commercial settlement uses $0.550\text{ g}$ ($1.5\%$), deducting recovery only on the excess: $0.595 - 0.550 = 0.045\text{ g}$.

### Laboratory Assay Corrections & Versioned Reconciliation Snapshots

When laboratory fire assay or XRF spectrometry is performed on a returned item:
1. `POST /api/v1/returns/{id}/assay` updates `MaterialReturn.assayed_fineness_ppt` and recalculates `fine_gold_g = net_metal_weight_g × assayed_fineness_ppt ÷ 1000`.
2. The original `declared_fineness_ppt` remains **immutable** for audit forensics.
3. Re-triggering `POST /api/v1/jobs/{id}/reconcile` creates an immutable new snapshot `REC-{code}-v2` with `run_number = 2` and `is_latest = true`.
4. The previous run `REC-{code}-v1` has its `is_latest` flag set to `false`, but all historical numbers, line items, and event references remain completely **immutable**.

### Prevention of Double-Counting in Settlements

The fine-gold reconciliation equation accounts for all metal:
$$\text{Actual Loss (Fine)} = \text{Total Issued Fine} - (\text{Finished Fine (Assayed)} + \text{Scrap Fine} + \text{WIP Fine})$$
This actual loss inherently captures both:
1. **Physical Loss:** $\text{Gross Issued Net Metal} - \text{Total Returned Net Metal}$
2. **Assay Purity Deficit:** $\text{Finished Net Metal} \times (\text{Declared Fineness} - \text{Assayed Fineness}) \div 1000$

Commercial recovery is computed directly against the single authoritative variance:
$$\text{Excess Loss Fine} = \max(0, \text{Actual Loss Fine} - \text{Contractual Wastage Allowance})$$
$$\text{Gold Recovery Deduction} = \text{Excess Loss Fine} \times \text{Gold Rate Applied}$$

The assay shortfall is **NOT** deducted a second time. Purity deficits simply reduce the accounted fine gold in the reconciliation equation, flowing mathematically into the single variance without double-counting.

Response:
```json
{
  "id": "f8821901-445a-4e2b-bb89-91a029384756",
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "runNumber": 1,
  "versionIdentifier": "REC-J-1160-v1",
  "status": "within_allowance",
  "totalIssuedGrossG": 40.201,
  "totalIssuedNetG": 40.201,
  "totalIssuedFineG": 36.824,
  "finishedJewelleryFineG": 15.114,
  "returnedScrapFineG": 21.450,
  "retainedScrapFineG": 0.137,
  "closingWipFineG": 0.0,
  "documentedLossFineG": 0.0,
  "expectedFineG": 36.824,
  "actualAccountedFineG": 36.701,
  "unexplainedVarianceFineG": 0.123,
  "variancePct": 0.3,
  "lossAllowancePct": 1.0,
  "lossAllowanceFineG": 0.368,
  "supportingEventIds": ["..."],
  "supportingReturnIds": ["..."],
  "supportingMeasurementIds": ["..."],
  "isLatest": true,
  "createdAt": "2026-11-13T10:45:00Z",
  "lineItems": [...]
}
```

### Compare Reconciliation Runs
`GET /api/v1/reconciliations/compare?run1Id={id}&run2Id={id}` → **200 OK**  
Side-by-side material balance diff tracking intermediate scrap and returns.

---

## 5. Exception Management & Lifecycle

### Detect Exceptions
`POST /api/v1/exceptions/detect?jobId={jobId}` → **200 OK**  
**Role:** `admin`, `manager`

Scans jobs for variances exceeding contractual allowance, purity mismatches, and overdue/unacknowledged transfers.

### Assign Investigator
`PATCH /api/v1/exceptions/{id}/assign` → **200 OK**  
`{"investigatorId": "<userId>"}`

### Attach Evidence
`POST /api/v1/exceptions/{id}/evidence` → **201 Created**  
`{"evidenceType": "assay_slip", "title": "Fire assay report", "fileUrl": "https://...", "details": {...}}`

### Resolve Exception
`POST /api/v1/exceptions/{id}/resolve` → **200 OK**  
`{"resolutionNotes": "Approved commercial deduction under schedule addendum"}`

### Dismiss Exception
`POST /api/v1/exceptions/{id}/dismiss` → **200 OK**  
`{"reason": "Tolerable variation justified by micro-filigree technique"}`

---

## 6. AI Investigation Assistant & Read-Only Tools

### Run AI Investigation
`POST /api/v1/investigations/run` → **201 Created**  
**Role:** `admin`, `manager`

Executes deterministic, read-only evidence inspection. Every fact and cause links directly to backend database IDs.

Request:
```json
{
  "exceptionId": "f026fe21-b3d6-4db9-a333-7aa77bc297d3"
}
```

Response:
```json
{
  "id": "bb441122-3344-5566-7788-9900aabbccdd",
  "exceptionId": "f026fe21-b3d6-4db9-a333-7aa77bc297d3",
  "jobId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
  "provider": "deterministic_evidence_v1",
  "confidence": 0.94,
  "createdAt": "2026-11-13T11:00:00Z",
  "response": {
    "summary": "Investigation for exception EX-J-1168-V (variance): Karigar returned 25.000 g against 30.251 g held custody.",
    "verifiedFacts": [
      {
        "fact": "Job J-1168 has total issued fine gold of 46.030 g with contractual loss allowance of 1.5%.",
        "recordId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
        "field": "lossAllowancePct",
        "observedValue": "1.5%"
      }
    ],
    "suspectedCauses": [
      {
        "cause": "Unaccounted filing or polishing process loss",
        "probability": 0.85,
        "rationale": "Physical custody was not completely returned to the vault."
      }
    ],
    "evidence": [
      {
        "evidenceType": "JobOrder",
        "recordId": "c52daee7-7182-48dc-89a1-cb6323cf1839",
        "field": "code",
        "observedValue": "J-1168"
      }
    ],
    "recommendedActions": [
      {
        "action": "Inspect karigar vacuum dust collectors and bench sweeps",
        "role": "VaultOperator",
        "priority": "High"
      }
    ],
    "limitations": [
      "The AI assistant does NOT have authority to alter ledger balances or approve settlements."
    ]
  }
}
```

---

## 7. Commercial Settlements

### Create Settlement Rule
`POST /api/v1/settlements/rules` → **201 Created**  
**Role:** `admin`, `manager`

Defines loss allowance percentage, making charges, and recovery gold rate per fine gram.

### Generate Settlement Worksheet
`POST /api/v1/settlements/worksheets` → **201 Created**  
**Role:** `admin`, `manager`

Calculates gross making charges, excess variance fine gold, recovery deductions, and net payable INR.

### Approve Settlement Worksheet
`POST /api/v1/settlements/worksheets/{id}/approve` → **200 OK**  
**Role:** `admin`, `manager`

Locks worksheet in `approved` status, records audit event, and updates job status to `settled`.

