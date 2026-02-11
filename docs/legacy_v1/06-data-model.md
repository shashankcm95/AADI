6 — Data Model & Access Patterns

This document explains what data we store, why it’s shaped this way, and how it is accessed efficiently.
It is written to prevent the most common DynamoDB failure mode: adding queries that the model cannot support.

Design Principles

Access-pattern first

Single-table per domain

Explicit state fields

TTL used only for cleanup, never correctness

No scans in production paths

Tables Overview
Table	Purpose
OrdersTable	Source of truth for order lifecycle
RestaurantConfigTable	Per-restaurant tuning
CapacityTable	Rolling prep capacity tracking
1. Orders Table
Table Name
arrive-*-OrdersTable

Primary Key
PK: order_id (string)

Why?

Orders are always uniquely addressed by ID

Simplifies idempotency

Keeps write paths simple

Core Attributes
Attribute	Type	Description
order_id	string	Primary identifier
restaurant_id	string	Owning restaurant
status	string	Order state
created_at	number	Epoch seconds
expires_at	number	Soft expiry
sent_at	number	When sent to restaurant
received_at	number	Restaurant ack time
vicinity	boolean	Customer proximity
prep_units_total	number	Capacity weight
total_cents	number	Price
items	list	Order contents
Order Status Values
Status	Meaning
PENDING_NOT_SENT	Created but not eligible
WAITING_FOR_CAPACITY	Blocked by throughput
SENT_TO_RESTAURANT	Accepted into kitchen
EXPIRED	TTL or business expiry

Status is not derived. It is explicit and authoritative.

Orders GSI
GSI: GSI_RestaurantStatus
PK: restaurant_id
SK: status

Access Patterns Supported

“Show me all SENT orders for restaurant”

“Show me all WAITING orders”

Kitchen dashboard views

Sorting

Results are sorted in application code by:

sent_at (preferred)

fallback: created_at

2. Restaurant Config Table
Table Name
arrive-*-RestaurantConfigTable

Primary Key
PK: restaurant_id

Attributes
Attribute	Type	Purpose
restaurant_id	string	Identifier
capacity_window_seconds	number	Window size
max_prep_units_per_window	number	Throughput cap
Why separate table?

Rarely changes

Read-heavy

Allows experimentation per restaurant

No impact on order write paths

3. Capacity Table
Table Name
arrive-*-CapacityTable

Composite Primary Key
PK: restaurant_id
SK: window_start (number)

Attributes
Attribute	Type	Description
restaurant_id	string	Owner
window_start	number	Rounded epoch
used_units	number	Reserved prep units
ttl	number	Auto-cleanup
Capacity Write Pattern

Atomic reservation:

ADD used_units :add
CONDITION used_units + :add <= :max


This ensures:

No overbooking

No locks

No race conditions

TTL Strategy
Table	TTL Field	Purpose
Orders	expires_at	Cleanup abandoned orders
Capacity	ttl	Drop old windows

TTL is best-effort.
Business logic never relies on TTL execution timing.

Forbidden Access Patterns

❌ Scan all orders
❌ Query capacity without window key
❌ Derive state from timestamps
❌ Cross-table transactions

Future-Proofing

This model supports:

Multiple prep lanes

Priority orders

Restaurant overrides

Predictive capacity models

Manual capacity release

Without table redesign.

Mental Model

Orders describe intent
Capacity describes reality
Config describes policy

Next Document

Next we document the API surface:

docs/04-api-reference.md

Endpoints

Request/response schemas

Status transitions

Error codes
