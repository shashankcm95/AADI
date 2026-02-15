```markdown
# Core Engine Contract

**Version:** 2.1
**Date:** 2026-02-12

This document defines the **utility-agnostic core** of Arrive: a capacity-gated decision engine that transitions work items through a deterministic state machine based on eligibility signals and provider capacity.

This contract is the foundation that enables future products (beyond dine-in) to reuse the same logic safely.

---

## 1) Purpose

The core engine is responsible for:

1. Accepting a **work item** (customer intent)
2. Waiting until an **eligibility signal** is true (e.g., vicinity)
3. Attempting an **atomic capacity reservation**
4. Either:
   - **Dispatching** the work item immediately, or
   - Returning a **wait plan** (retry guidance), or
   - Rejecting due to expiration

The core engine is intentionally agnostic to:
- Restaurants vs other providers (clinics, barbers, retail, services)
- GPS vs BLE vs QR vs manual check-in
- “Order” vs “Appointment” vs “Ticket”

---

## 2) Neutral Vocabulary

### WorkItem (generic)
A unit of intent that may become dispatchable.

Required logical fields:
- `work_item_id`
- `provider_id` (capacity owner)
- `state`
- `created_at`
- `expires_at`
- `work_units_total` (load weight)
- `eligibility` (boolean or enum)
- `dispatch_at` (when dispatched, if ever)

### ProviderConfig (policy)
Per-provider gating policy:
- `window_seconds`
- `max_units_per_window`
- optional signal policy fields (future)

### CapacityWindow (accounting)
Capacity ledger keyed by:
- `(provider_id, window_start)`
- `used_units`
- `ttl` (cleanup only)

---

## 3) Inputs

### Eligibility Signal
A generic version of “vicinity”.

Input shape:
- `eligibility: boolean`
- optional metadata: `signal_type`, `confidence` (future)

Contract:
- Eligibility is not assumed continuously.
- Client provides eligibility only when needed.

---

## 4) Outputs (Decisions)

When eligibility becomes true, the engine yields exactly one outcome:

### A) Dispatch Now
- Reserve capacity atomically
- Transition state → `DISPATCHED`
- Persist `dispatch_at`
- Return success payload

### B) Wait
- Transition state → `WAITING`
- Persist `waiting_since` + `suggested_start_at`
- Return retry guidance to the client

### C) Expire / Reject
- If `now > expires_at` → `EXPIRED` (best-effort update)
- Return a conflict response to the client

---

## 5) State Machine (Generic)

States:
- `CREATED`  (maps to `PENDING_NOT_SENT`)
- `WAITING`  (maps to `WAITING_FOR_CAPACITY`)
- `DISPATCHED` (maps to `SENT_TO_DESTINATION`)
- `EXPIRED`

Allowed transitions:
- `CREATED → DISPATCHED`
- `CREATED → WAITING`
- `WAITING → DISPATCHED`
- `ANY → EXPIRED`

Forbidden transitions:
- `DISPATCHED → CREATED/WAITING`
- `EXPIRED → ANY`

---

## 6) Capacity Contract (Invariants)

These invariants must hold for all utilities:

1. **No overbooking**
   - For a given `(provider_id, window_start)`:
     `used_units + add_units <= max_units`

2. **At-most-once dispatch**
   - A work item can only be dispatched once.
   - No duplicate capacity reservation for the same work item.

3. **Fail-safe behavior**
   - If capacity reservation fails due to an error, treat as `WAIT` (never dispatch).

4. **TTL is not correctness**
   - TTL cleanup is best-effort and must not be required for correctness.

---

## 7) Utility-Specific Mapping (Current Dine-In)

| Generic Concept | Current System |
|---|---|
| Provider | Restaurant |
| WorkItem | Order |
| Eligibility | Vicinity |
| Work units | Prep units |
| Dispatched | Sent to restaurant |

This mapping keeps v1 understandable while enabling later extraction into a true platform core.

---
```