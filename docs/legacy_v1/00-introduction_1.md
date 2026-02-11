# Arrive — Technical Documentation

> This documentation follows best practices for modern backend systems:
>
> * Clear separation of **conceptual docs** vs **reference docs**
> * Explicit **contracts** (APIs, states, invariants)
> * Designed to scale as complexity grows
> * Written for engineers first

---

## Documentation Philosophy

This documentation is structured to answer **four different questions**, each in its own place:

1. **What is the system and why does it exist?**
   → Introduction & System Overview

2. **How does the system work internally?**
   → Order lifecycle, capacity model, data model

3. **How do I interact with the system?**
   → API reference (endpoints, requests, responses)

4. **How do I operate and extend it safely?**
   → Operational notes, invariants, future considerations

This separation prevents a common failure mode in growing systems where API docs, design rationale, and implementation details become tangled and outdated.

---

## Proposed Documentation Structure (Best Practice)

```
docs/
├── 00-introduction.md          # Product intent & non-goals
├── 01-system-overview.md       # High-level architecture & request flow
├── 02-repo-structure.md        # Codebase layout & ownership
├── 03-order-lifecycle.md       # Order states & transitions (authoritative)
├── 04-capacity-model.md        # Capacity windows & reservation logic
├── 05-api-reference.md         # REST endpoints & contracts
├── 06-data-model.md            # DynamoDB schemas & GSIs
├── 07-operational-notes.md     # TTLs, retries, failure modes
└── 08-future-considerations.md # Deferred ideas & conscious trade-offs
```

Each file has **one job** and should be updateable without touching others.

---

## Documentation Conventions

### 1. Source of Truth

* **Order lifecycle** → `03-order-lifecycle.md`
* **Capacity logic** → `04-capacity-model.md`
* **API contracts** → `05-api-reference.md`

If behavior is undocumented, it is considered **undefined**.

---

### 2. API Documentation Rules

API docs will:

* Describe **intent first**, then request/response
* Include **example payloads**
* Explicitly document **state preconditions**
* Never rely on implementation details

Example format:

```
POST /v1/orders

Purpose:
  Create a new order in PENDING_NOT_SENT state

Preconditions:
  - restaurant_id must exist
  - items must be non-empty

Responses:
  201 Created
  400 Validation Error
```

---

### 3. State Machines Are Explicit

Order state transitions are treated as a **state machine**, not implicit behavior.

If a transition is not listed in documentation, it is considered invalid even if the code allows it.

---

### 4. Forward-Compatible Language

Docs will:

* Avoid hard promises where iteration is expected
* Clearly mark prototype assumptions
* Separate **current behavior** from **future intent**


