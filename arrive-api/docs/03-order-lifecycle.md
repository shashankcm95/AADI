03 — Order Lifecycle & State Machine

This document defines the authoritative order state machine for Arrive.

If code and documentation ever disagree, this document wins.

Core Philosophy

Arrive treats an order as a stateful contract, not a fire-and-forget request.

Key principles:

Every order is always in exactly one state

State transitions are explicit and guarded

Capacity is reserved only when the customer is physically near

Restaurants are protected from overload by design

Order States (Authoritative)
State	Meaning
PENDING_NOT_SENT	Order exists but has not been sent to restaurant
WAITING_FOR_CAPACITY	Customer is nearby, but restaurant is at capacity
SENT_TO_RESTAURANT	Capacity reserved and order delivered to kitchen
EXPIRED	Order timed out before being sent
State Diagram (Conceptual)
PENDING_NOT_SENT
      |
      | vicinity = true
      v
 ┌────────────────────┐
 │ capacity available │───▶ SENT_TO_RESTAURANT
 └────────────────────┘
      |
      | capacity full
      v
WAITING_FOR_CAPACITY
      |
      | retry after suggested time
      v
(re-attempt capacity reservation)

State Definitions (Detailed)
1. PENDING_NOT_SENT

Entry conditions

Order created successfully

expires_at set

vicinity = false

Allowed transitions

→ SENT_TO_RESTAURANT

→ WAITING_FOR_CAPACITY

→ EXPIRED

Forbidden transitions

Cannot skip directly to EXPIRED without time check

Cannot return to this state once left

2. WAITING_FOR_CAPACITY

Meaning

Customer is nearby

Restaurant is currently at prep capacity

System provides deterministic retry guidance

Required fields

waiting_since

suggested_start_at

vicinity = true

Allowed transitions

→ SENT_TO_RESTAURANT (capacity frees up)

→ EXPIRED

Important invariant

No capacity is reserved while in this state.

3. SENT_TO_RESTAURANT

Meaning

Capacity has been atomically reserved

Restaurant has received the order

Kitchen work may begin

Required fields

sent_at

capacity_window_start

received_by_restaurant = true

Allowed transitions

None (terminal for v1)

Design note

We intentionally do not support rollback from this state.

4. EXPIRED

Meaning

Order exceeded its TTL before being sent

No capacity was consumed

Allowed transitions

None (terminal)

Transition Rules (Formal)
PENDING_NOT_SENT → SENT_TO_RESTAURANT

Guards

vicinity == true

Order not expired

Capacity reservation succeeds atomically

Side effects

Reserve prep units

Write sent_at

Lock capacity window

PENDING_NOT_SENT → WAITING_FOR_CAPACITY

Guards

vicinity == true

Capacity reservation fails

Side effects

Compute suggested_start_at

Persist retry guidance

WAITING_FOR_CAPACITY → SENT_TO_RESTAURANT

Guards

Retry call after suggested_start_at

Capacity reservation succeeds

ANY → EXPIRED

Guards

now > expires_at

Side effects

Best-effort status update

Capacity Interaction (Critical)

Capacity is:

Windowed (default: 10 minutes)

Atomic

Idempotent per order attempt

Never double-counted

Invariant

An order may consume capacity at most once.

Idempotency & Safety

Repeating /vicinity calls is safe

Capacity checks are atomic

State transitions are guarded by DynamoDB conditions

Partial failures converge to a correct state

Why This Model Works

Customers get predictable timing

Restaurants avoid surprise overload

System behavior is explainable

Failures are recoverable

This lifecycle is intentionally boring — and that’s exactly what makes it reliable.

Next Document

Next we’ll document API Endpoints precisely:

docs/04-api-reference.md

Routes

Request/response schemas

Status codes

Error semantics

Idempotency guarantees
