05 — Repository Structure & Code Ownership

This document explains how the repo is organized, why each file exists, and where future changes should go as the system grows.

Goal:
Any engineer should be able to land in this repo and confidently know where to read, where to change, and where not to touch.

Top-Level Structure
arrive-api/
├── infrastructure/
├── src/
├── docs/
├── scripts/
├── template.yaml
├── README.md
└── .gitignore

infrastructure/

Purpose:
Infrastructure-as-Code (IaC) definitions that describe what exists in AWS.

infrastructure/
├── dynamodb.yaml
├── iam.yaml
└── outputs.yaml

Responsibilities

DynamoDB tables

Indexes

IAM roles & permissions

Outputs consumed by the app

Rules

❌ No business logic

❌ No environment-specific hacks

✅ Safe to redeploy at any time

src/

Purpose:
All runtime application code.

src/
├── app.py
├── orders/
│   ├── create_order.py
│   ├── update_vicinity.py
│   └── list_orders.py
├── capacity/
│   ├── reserve_capacity.py
│   └── capacity_window.py
└── utils/
    ├── responses.py
    ├── time.py
    └── validation.py


Even if some logic currently lives in app.py, this is the target shape as complexity increases.

src/app.py

Purpose:
Lambda entry point + routing only.

Responsibilities:

Parse request

Route to correct handler

Return HTTP response

Non-responsibilities:

❌ Business rules

❌ DynamoDB condition logic

❌ Capacity math

If app.py grows beyond routing, it’s a refactor smell.

src/orders/

Purpose:
Order lifecycle logic.

create_order.py

Input validation

Order normalization

Initial persistence

No capacity checks

update_vicinity.py

State transitions

Capacity gating

Idempotency enforcement

list_orders.py

Read-only queries

GSI usage

Sorting rules

Rule: Order state transitions must live here — nowhere else.

src/capacity/

Purpose:
Restaurant throughput modeling.

reserve_capacity.py

Atomic DynamoDB updates

Conditional expressions

Window enforcement

capacity_window.py

Window start calculation

TTL logic

Time rounding rules

Capacity logic is isolated so it can later be replaced with:

ML predictions

Manual overrides

Restaurant-specific policies

src/utils/

Purpose:
Pure helpers with no AWS side effects.

Examples

Response formatting

Timestamp helpers

Validation helpers

Decimal → JSON handling

If a file imports boto3, it does not belong here.

docs/

Purpose:
Living documentation.

docs/
├── 01-overview.md
├── 02-system-design.md
├── 03-state-machine.md
├── 04-api-reference.md
├── 05-repo-structure.md
└── 06-data-model.md

Rules

Docs change with code

PRs touching logic should update docs

Docs are versioned with the system

scripts/

Purpose:
Operational helpers (local-only).

Examples:

Seed restaurant configs

Reset capacity windows

Backfill test data

Scripts are allowed to be ugly. Production code is not.

template.yaml

Purpose:
AWS SAM / CloudFormation root template.

Defines:

Lambda functions

Environment variables

Table bindings

Permissions

Treat this as deployment glue, not logic.

README.md

Purpose:
Onboarding & quickstart.

Contains:

What Arrive is

How to deploy

How to run curl tests

Link to docs/

Ownership & Change Rules
Adding a new API endpoint

Add route in app.py

Create handler in appropriate domain folder

Update docs/04-api-reference.md

Changing order behavior

Must update:

State machine doc

API reference

Tests (when added)

Changing capacity rules

Must update:

capacity/

Data model doc

Migration plan if breaking

Design Philosophy Recap

Thin entry points

Explicit state transitions

Isolated throughput logic

Docs are first-class citizens

Next Document

Next we formalize the Data Model:

docs/06-data-model.md

DynamoDB tables

GSIs

Access patterns

TTL strategy
