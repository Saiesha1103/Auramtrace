# AURUMTRACE — Frontend Integration Contract & Guide

This document defines the interface boundary and integration contract between the **AURUMTRACE Frontend** (`src/`) and the **AURUMTRACE FastAPI Backend** (`backend/`).

---

## 1. Core Conventions & Data Types

| Topic | Frontend (`src/`) | Backend (`backend/`) | Conversion Rule |
|---|---|---|---|
| **Fineness** | Decimal fraction `0.916` (22K), `0.995` (24K) | Parts per thousand `916.0`, `995.0` | **Frontend → Backend:** `fineness * 1000`<br>**Backend → Frontend:** `finenessPpt / 1000` |
| **Weights** | Decimal numbers in **grams** | Decimal numbers in **grams** | Exactly **3 decimal places** (0.001 g precision). Values with > 3 decimals are rejected by the backend. |
| **Stone Weight** | Implicit or subtracted | Explicit `stoneWeightG = grossWeightG - netMetalWeightG` | **Stones are never gold.** Net metal weight is always used for gold balance and fineness math. |
| **JSON Keys** | camelCase (`jobId`, `netMetalWeightG`) | camelCase (`jobId`, `netMetalWeightG`) | Pydantic models automatically serialize to and deserialize from camelCase. |
| **IDs** | UUID strings (`"2eeef155-..."`) | UUID strings (`"2eeef155-..."`) | 128-bit UUID strings. Human-readable codes (`"J-1160"`, `"K-01"`, `"L-3279"`) are stored in `code`. |
| **Percentages** | Number (`1.0` for 1%) | Number (`1.0` for 1%) | 0.0% to 100.0% represented directly as numbers. |
| **Timestamps** | ISO-8601 UTC strings (`"2026-11-13T10:00:00Z"`) | ISO-8601 UTC strings (`"2026-11-13T10:00:00Z"`) | All dates in UTC with explicit timezone indicator. |

---

## 2. Model Mapping Matrix

### Karigars & Parties

| Frontend `Party` (`src/app/data/types.ts`) | Backend `KarigarOut` | Notes |
|---|---|---|
| `id` | `id` | UUID string |
| `name` | `name` | Artisan / workshop name |
| `role` | `kind` | `'Head karigar'` ↔ `'head_karigar'`<br>`'Karigar'` ↔ `'karigar'`<br>`'Subcontractor'` ↔ `'subcontractor'` |
| `parentId` | `headKarigarId` | Head karigar UUID |
| `unit` | `unit` | Workshop location |
| `skills` | `skills` | Array of skill strings |
| — | `custody.netWeightG` | Live derived gold balance held by this karigar |
| — | `custody.fineGoldG` | Fine gold equivalent held |

### Job Orders

| Frontend `Job` | Backend `JobOrderOut` | Notes |
|---|---|---|
| `id` | `id` | UUID string |
| `title` | `title` | Job description |
| `orderRef` | `code` | Unique job code (`"J-1160"`) |
| `karat` | `karat` | `'24K'`, `'22K'`, `'18K'`, `'14K'` |
| `fineness` | `targetFinenessPpt` | `0.916` ↔ `916.0` |
| `pieces` | `pieces` | Integer quantity |
| `targetGrossPerPiece` | `targetGrossPerPieceG` | Target weight per piece |
| `headKarigarId` | `headKarigarId` | Assigned head karigar |
| `lossAllowancePct` | `lossAllowancePct` | Contractual loss tolerance (e.g. `1.0`%) |
| `status` | `status` | `'Draft'` ↔ `'draft'`, `'Issued'` ↔ `'issued'`, `'In production'` ↔ `'in_production'`, `'Returned'` ↔ `'returned'`, `'Reconciled'` ↔ `'reconciled'`, `'Settled'` ↔ `'settled'` |
| `deadline` | `dueDate` | `YYYY-MM-DD` |
| `parentId` | `parentJobId` | For split jobs, points to parent job |

### Material Transfers

| Frontend `Transfer` | Backend `MaterialEvent` (`event_type="transfer"`) | Notes |
|---|---|---|
| `id` | `id` | UUID string |
| `jobId` | `jobId` | Associated job UUID |
| `from` | `fromKarigarId` | Sender karigar UUID |
| `to` | `toKarigarId` | Receiver karigar UUID |
| `gross` | `grossWeightG` | Gross weight in grams |
| `fineness` | `finenessPpt` | `0.916` ↔ `916.0` |
| `kind` | `metadata.transferKind` | `'Full'`, `'Partial'`, `'Split'` |
| `purpose` | `note` | Transfer notes / challan reference |
| — | `state` | `'pending'` (unacknowledged), `'acknowledged'`, or `'reversed'` |

### Production Tracking

| Frontend `ProductionEntry` | Backend `ProductionEntryOut` | Notes |
|---|---|---|
| `id` | `id` | Entry UUID |
| `jobId` | `jobId` | Associated job UUID |
| `stage` | `stage` | e.g. `'Melting'`, `'Casting'`, `'Filing'`, `'Setting'`, `'Polishing'`, `'QC'` |
| `partyId` | `karigarId` | Karigar performing work |
| `inGross` | `inputGrossWeightG` | Gross weight at stage start |
| `outGross` | `outputGrossWeightG` | Gross weight at stage completion |
| `pieces` | `pieces` | Pieces processed |
| `status` | `status` | `'In progress'` ↔ `'in_progress'`, `'Done'` ↔ `'completed'` |

### Reconciliation Engine

| Frontend View | Backend `ReconciliationRunOut` | Formula / Source |
|---|---|---|
| Total Issued Fine Gold | `totalIssuedFineG` | $\sum (\text{Net Metal Weight} \times \text{Fineness} \div 1000)$ of issues minus reversals |
| Finished Goods Fine Gold | `finishedJewelleryFineG` | From `MaterialReturn` where `returnCategory="finished_jewellery"` |
| Returned Scrap Fine Gold | `returnedScrapFineG` | From `MaterialReturn` where `returnCategory in ("scrap", "dust")` |
| Retained Scrap Fine Gold | `retainedScrapFineG` | Documented scrap retained in workshop custody |
| Closing WIP Fine Gold | `closingWipFineG` | Declared WIP returns |
| Documented Process Loss | `documentedLossFineG` | Documented losses from stage measurements |
| Unexplained Variance | `unexplainedVarianceFineG` | $\text{Issued} - \text{Accounted}$ |
| Variance Percentage | `variancePct` | $\text{Variance} \div \text{Issued} \times 100$ |
| Contractual Allowance | `lossAllowanceFineG` | $\text{Issued} \times \text{lossAllowancePct} \div 100$ |
| Status | `status` | `'within_allowance'`, `'above_allowance'`, `'fineness_mismatch'`, `'unacknowledged_transfer'` |

---

## 3. Authentication & API Client Setup

### Storing and Using Tokens
When a user logs in via `POST /api/v1/auth/login`:
```json
{
  "email": "manager@aurumtrace-demo.example.com",
  "password": "Aurum-Demo-2026!"
}
```
The response returns:
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIsIn...",
  "tokenType": "bearer",
  "expiresIn": 3600
}
```
Store `accessToken` in `localStorage.setItem('aurum_token', res.accessToken)`.
Include the token in all API requests:
```
Authorization: Bearer <accessToken>
```

---

## 5. Frontend Screens & API Endpoint Mapping

| Screen / Feature | UI Route / Component | Backend API Endpoints | Data Contract / Formatting |
|---|---|---|---|
| **Vault & Custody** | `AppShell` -> Vault Overview | `GET /api/v1/lots`<br>`POST /api/v1/lots`<br>`POST /api/v1/lots/{id}/issue`<br>`POST /api/v1/events/{id}/acknowledge` | Weights formatted with 3 decimals (`0.000 g`). Stones tracked separately. |
| **Karigar Directory** | `AppShell` -> Karigars | `GET /api/v1/karigars`<br>`GET /api/v1/karigars/hierarchy`<br>`POST /api/v1/karigars` | Live derived gold holdings displayed per karigar node. |
| **Job Orders** | `AppShell` -> Jobs | `GET /api/v1/jobs`<br>`POST /api/v1/jobs`<br>`GET /api/v1/jobs/{id}` | Status badge maps `draft`, `issued`, `in_production`, `returned`, `reconciled`, `settled`. Displays manufacturing loss allowance (`lossAllowancePct`). |
| **Material Transfers** | `AppShell` -> Transfers | `GET /api/v1/transfers`<br>`POST /api/v1/transfers`<br>`POST /api/v1/transfers/{id}/acknowledge`<br>`POST /api/v1/transfers/{id}/reverse` | Shows pending/acknowledged state. Lineage tracks from/to karigar IDs. |
| **Production Tracking** | `AppShell` -> Production | `GET /api/v1/production/measurements`<br>`POST /api/v1/production/measurements` | In/Out net metal weight and process stage. |
| **Material Returns** | `AppShell` -> Returns | `GET /api/v1/returns`<br>`POST /api/v1/returns`<br>`POST /api/v1/returns/{id}/assay` | Categories: `finished_jewellery`, `scrap`, `dust`, `wip`. Assay updates show declared vs assayed fineness. |
| **Reconciliation Engine** | `AppShell` -> Reconciliation | `POST /api/v1/jobs/{id}/reconcile`<br>`GET /api/v1/reconciliations`<br>`GET /api/v1/reconciliations/compare` | Displays fine gold balance equation. Clearly labels `lossAllowancePct` as **"Manufacturing Allowance"**. Shows historical versions (`v1`, `v2`). |
| **Exceptions & AI** | `AppShell` -> Exceptions | `POST /api/v1/exceptions/detect`<br>`GET /api/v1/exceptions`<br>`POST /api/v1/investigations/run`<br>`POST /api/v1/exceptions/{id}/resolve` | AI assistant provides verified facts grounded in database record IDs. |
| **Commercial Settlements** | `AppShell` -> Settlements | `POST /api/v1/settlements/rules`<br>`GET /api/v1/settlements/rules`<br>`POST /api/v1/settlements/worksheets`<br>`POST /api/v1/settlements/worksheets/{id}/approve` | Amounts formatted as Indian Rupees (`₹#,##0.00`). Clearly labels `wastageAllowanceFineG` as **"Contractual Wastage Allowance"**. |

### Formatting Standards in UI
- **Grams:** `value.toFixed(3) + " g"` (e.g. `24.500 g`). Never truncate or round to 2 decimals.
- **Fineness:** `(value / 1000).toFixed(3)` for decimal fraction or `value.toFixed(1) + " ppt"` for millesimal fineness.
- **Currency:** `new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value)` (e.g. `₹11,025.00`).

