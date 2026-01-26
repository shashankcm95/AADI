# Arrive API

Arrive is a **capacity-gated dispatch system** that safely transitions customer intent into provider work, based on eligibility signals and real-time capacity.

The system is designed around a **utility-agnostic core**, with dine-in restaurants as the first concrete implementation.

---

## What This Repo Is

This repository contains:
- A serverless API (AWS Lambda + API Gateway)
- A deterministic state machine for work dispatch
- A capacity accounting system that prevents overbooking
- A clean seam for future utilities beyond restaurants

Current utility:
- **Dine-in restaurant order dispatch**

Future utilities (by design):
- Appointments
- Retail pickup
- Service queues
- Any capacity-bound workflow

---

## Core Idea (One Paragraph)

A work item (order) is created in a neutral pending state.  
When an eligibility signal becomes true (e.g., customer is nearby), the system attempts to **atomically reserve capacity** for the current time window.  

If capacity is available, the work item is dispatched immediately.  
If not, the system returns **wait guidance** instead of failing or overbooking.

---

## System Status

**Milestone:** `milestone-capacity-v1`

✔ Capacity-gated dispatch  
✔ Atomic reservations  
✔ Auto-ack on dispatch  
✔ Stable core APIs  
✔ Deterministic state transitions  

This milestone represents a **stable foundation** for future growth.

---

## Documentation Index

All authoritative documentation lives in `/docs`.

| Doc | Purpose |
|---|---|
| [`core-engine-contract.md`](docs/core-engine-contract.md) | Utility-agnostic engine contract |
| `01-overview.md` | System overview & mental model |
| `02-architecture.md` | High-level architecture |
| `03-data-model.md` | DynamoDB tables & indexes |
| `04-api-reference.md` | API endpoints & payloads |
| `05-state-machine.md` | Order lifecycle |
| `06-capacity-model.md` | Windowing & reservation logic |
| `09-operational-notes.md` | Deployment & ops notes |
| `10-future-considerations.md` | Planned evolution |

---

## Running Locally

```bash
sam build
sam local start-api

\# Environment variables:

ORDERS_TABLE
RESTAURANT_CONFIG_TABLE
CAPACITY_TABLE

(See docs/09-operational-notes.md for full setup.)

\## Design Principles
Safety over throughput
No implicit dispatch
Capacity is a hard invariant
Core logic remains utility-agnostic
APIs are explicit and idempotent

\##Repo Structure (High Level)
arrive-api/
├── app.py            # Lambda entrypoint
├── template.yaml     # SAM template
├── docs/             # All documentation
├── events/           # Test payloads
└── README.md
Contributing
This repo intentionally favors:

Explicit state transitions

Clear invariants

Small, verifiable changes

If a change breaks any invariant described in core-engine-contract.md,
it should be considered a breaking change.