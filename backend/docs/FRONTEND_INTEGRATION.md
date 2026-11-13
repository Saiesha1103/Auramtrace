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

## 4. Running Frontend and Backend Together Locally

1. **Start Backend (Terminal 1):**
   ```bash
   cd backend
   source .venv/bin/activate
   alembic upgrade head
   python -m scripts.seed
   uvicorn app.main:app --reload --port 8000
   ```

2. **Start Frontend (Terminal 2):**
   ```bash
   cd ..
   export VITE_API_BASE_URL=http://localhost:8000/api/v1
   npm run dev
   ```
   Open `http://localhost:5173` in your browser.
