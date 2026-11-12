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
