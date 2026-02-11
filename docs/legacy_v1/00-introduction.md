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

## What This Documentation Covers

This documentation explains:

* How the system is structured
* How orders move through the system
* How capacity is enforced
* How APIs are expected to behave

It is written to be:

* Easy to onboard new contributors
* Safe to extend without breaking guarantees
* Honest about trade-offs and limitations

---

## Where to Go Next

* **02-repo-structure.md** → Learn how the repository is organized
* **03-order-lifecycle.md** → Understand order states and transitions
* **04-capacity-model.md** → Dive into the capacity enforcement logic

---

> If you are reading this to modify behavior, start with the order lifecycle.
> If you are reading this to scale the system, start with the capacity model.

