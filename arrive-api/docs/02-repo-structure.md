02 — Repository Structure
Top-Level Layout
AADI/
├── arrive-api/
│   ├── template.yaml
│   ├── src/
│   │   ├── orders/
│   │   │   └── app.py
│   │   ├── restaurants/
│   │   │   └── app.py
│   │   └── health/
│   │       └── app.py
│   ├── scripts/
│   │   └── seed/
│   │       ├── seed_menu.sh
│   │       └── menu_item.json
│   ├── samconfig.toml
│   └── README.md
├── docs/
│   ├── 01-system-overview.md
│   └── 02-repo-structure.md
└── .gitignore


This structure is intentional and optimized for:

AWS SAM deployment

Clear service boundaries

Minimal coupling between domains

arrive-api/ — Infrastructure + Runtime Code

This directory contains everything that is deployed.

template.yaml

Role:
AWS SAM template defining:

Lambda functions

API Gateway routes

DynamoDB tables

IAM permissions

Environment variables

Why this matters:

It is the single source of truth for infrastructure

No hidden resources exist outside this file

Changes here should be treated as system-level changes

src/ — Lambda Source Code

Each domain gets its own folder.

This prevents:

God Lambdas

Circular dependencies

Accidental cross-domain coupling

src/orders/app.py

Domain: Orders lifecycle + capacity gating

Responsibilities:

Create orders

Handle proximity (vicinity) updates

Enforce capacity windows

Transition order states

List orders by restaurant & status

Key concepts implemented here:

Order state machine

Atomic capacity reservation

Expiry enforcement

Deterministic retry guidance

This file is the core brain of the system.

src/restaurants/app.py

Domain: Restaurant-facing views

Responsibilities:

Fetch restaurant orders

Filter by status

Present kitchen-ready queues

Important constraint:

This Lambda never mutates capacity

It is read-oriented and safe

src/health/app.py

Domain: Operational health

Responsibilities:

Lightweight health checks

Deployment verification

Monitoring hooks

Why it exists separately:

Avoids coupling system health to business logic

Keeps uptime checks cheap and reliable

scripts/seed/ — Non-Production Utilities
scripts/seed/
├── seed_menu.sh
└── menu_item.json


Purpose:

Manual development seeding

Testing workflows

Local or sandbox environments only

Important rules:

These files are not runtime dependencies

They must not be referenced by Lambda code

JSON seed data should be gitignored if it becomes environment-specific

docs/ — Living Documentation

This folder is not optional.

Each file is:

Versioned with the code

Reviewed alongside PRs

Expected to evolve as features evolve

Recommended conventions:

01-xx.md → conceptual foundations

02-xx.md → structure and architecture

03-xx.md → behavior and flows

04-xx.md → APIs

05-xx.md → operational guarantees

.gitignore

Key principles:

Ignore build artifacts (.aws-sam/)

Ignore environment-specific seeds

Ignore credentials or local configs

This ensures:

Clean diffs

Safe collaboration

Reproducible environments

How to Add New Features Safely

When extending the system:

New Domain?

Create:

src/<domain>/app.py


Add:

A new Lambda

Explicit routes

Clear ownership

New Behavior in Orders?

Extend orders/app.py

Update documentation first

Add state transitions explicitly

New Infrastructure?

Update template.yaml

Treat as a breaking-change surface

Document assumptions immediately

Why This Structure Scales

Domains are isolated

Deployment remains predictable

Debugging is localized

Documentation mirrors reality

This repo will stay understandable even as the system grows.

Next Document

Next we’ll define the Order State Machine formally:

docs/03-order-lifecycle.md

States

Transitions

Guards

Failure cases

Invariants
