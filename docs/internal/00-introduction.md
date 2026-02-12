```markdown
# Arrive – System Introduction

## What Arrive Is

Arrive is a **capacity-aware ordering and arrival coordination system** for restaurants.

Its core goal is to reduce customer wait time and kitchen overload by **aligning when a customer arrives with when the restaurant can realistically prepare the order** — without requiring real-time, manual interaction from restaurant staff.

Arrive intentionally favors **predictability and reliability over precision**.

---

## The Core Problem

Restaurants experience unpredictable spikes in demand.

Customers experience:

* Orders that are accepted but not realistically startable
* Long waits after arrival
* Unclear guidance on *when* to show up

Restaurants experience:

* Kitchen overload
* Staff interruptions
* Manual triage during peak windows

Arrive addresses this by **controlling when orders are sent to the restaurant**, not just when they are placed.

---

## Key Design Principles

### 1. Capacity-First, Not Order-First

Orders are gated by **available preparation capacity**, not by time alone.

A restaurant defines how much work it can handle per time window, and Arrive enforces that limit strictly.

---

### 2. Customer-Initiated Flow

The system is driven by **customer intent**, not restaurant action.

* Customers place an order
* Customers indicate proximity (`vicinity = true`)
* The system decides whether the order can be sent now or should wait

Restaurants are not required to acknowledge or manage orders in real time.

---

### 3. Predictable Over Perfect

Arrive does **not** attempt to perfectly predict readiness.

Instead, it provides:

* Clear status transitions
* Conservative capacity limits
* Honest deferrals when overloaded

This mirrors successful patterns used by large platforms (e.g., “ready in ~15–20 minutes”).

---

### 4. Minimal Restaurant Overhead

Restaurants:

* Do not accept or reject orders
* Do not manage queues
* Do not interact with capacity controls

Arrive assumes:

> If an order is sent, the restaurant can and should start preparing it.

---

## Explicit Non‑Goals (v1)

Arrive intentionally does **not** support the following in its current phase:

* Manual order acceptance by restaurants
* Real-time kitchen progress tracking
* Staff-driven load adjustments during service
* Order cancellation and capacity rollback

These are deferred to future versions once the core model proves reliable.

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

---

## Documentation Map

**1. Context & Architecture**
- **00-introduction.md** — Product intent & non-goals
- **01-system-overview.md** — High-level architecture & request flow
- **11-system-design.md** — Detailed v2.1 system design
- **core-engine-contract.md** — Utility-agnostic core logic

**2. Core Mechanics**
- **03-order-lifecycle.md** — Order states & transitions (authoritative)
- **07-capacity-and-throughput.md** — Capacity windows & reservation logic
- **06-data-model.md** — DynamoDB schemas & access patterns

**3. Interfaces & Code**
- **02-repo-structure.md** — Codebase layout & ownership
- **04-api-reference.md** — REST endpoints & contracts
- **user_manual.md** — End-user usage guide
- **guide_google_auth.md** — Auth setup guide

**4. Operations & Reliability**
- **08-error-handling-retries-idempotency.md** — Failure modes & guarantees
- **09-operational-notes.md** — Deployment & runtime notes
- **10-future-considerations.md** — Roadmap & trade-offs

---

> If you are reading this to modify behavior, start with the order lifecycle.
> If you are reading this to scale the system, start with the capacity model.

**Version:** 2.1
**Date:** 2026-02-12

```