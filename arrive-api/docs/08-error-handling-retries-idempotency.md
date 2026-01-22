08 — Error Handling, Retries & Idempotency

This section defines how Arrive behaves under failure, retries, partial execution, and concurrency — and what guarantees the system provides to callers.

This is critical for:

Client correctness

Operational safety

Long-term maintainability

1. Design Principles

Arrive follows four strict rules:

Never double-book capacity

Never regress order state

Retries must be safe

Failures must be explicit

If a request is retried:

The system must converge to the same state

No side effects may be duplicated

2. Idempotency Model
What Is Idempotent in Arrive?
Operation	Idempotent?	Why
Create order	❌	New order = new intent
Update vicinity (true)	✅	State-guarded
Update vicinity (false)	✅	Overwrite-safe
Capacity reservation	✅	Conditional
List orders	✅	Read-only
Key Technique: Conditional Writes

State transitions are guarded using DynamoDB conditions:

Only transition if current status == expected status


This prevents:

Duplicate transitions

Race-condition corruption

Lambda retry side effects

3. Retry Scenarios
Scenario 1: Client Retries /vicinity

Cause:

Network timeout

Mobile reconnect

App background → foreground

Behavior:

Capacity reservation either already exists or is attempted once

Order remains in correct terminal state

No duplicate sends

Result:
✅ Safe retry

Scenario 2: Lambda Retries

Cause:

Transient AWS error

Timeout mid-execution

Behavior:

DynamoDB conditional expressions block double updates

Capacity table enforces upper bounds

Result:
✅ Safe retry

Scenario 3: Partial Success

Example:

Capacity reserved

Order update fails

Recovery Path:

Order reloaded

State re-evaluated

Response reflects authoritative state

Result:
✅ Eventually consistent, never incorrect

4. Error Categories

Arrive errors fall into four classes.

4.1 Validation Errors (4xx)

Returned when input is invalid.

Example:

{
  "error": {
    "code": "VALIDATION",
    "message": "items must be a non-empty list"
  }
}


Characteristics:

Client fault

Not retryable

Deterministic

4.2 Not Found Errors (404)

Returned when referencing missing resources.

Example:

{
  "error": {
    "code": "NOT_FOUND",
    "message": "order not found"
  }
}


Characteristics:

Safe failure

Indicates stale or invalid client state

4.3 Conflict Errors (409)

Returned when an operation violates state constraints.

Example:

{
  "error": {
    "code": "EXPIRED",
    "message": "order expired"
  }
}


Characteristics:

Business-rule enforcement

Client should abandon or restart flow

4.4 Internal Errors (5xx)

Returned when execution fails unexpectedly.

Example:

{
  "message": "Internal Server Error"
}


Characteristics:

Logged with stack trace

Retried automatically by infrastructure

Should not corrupt state

5. State Transition Safety
Allowed Transitions
PENDING_NOT_SENT → SENT_TO_RESTAURANT
PENDING_NOT_SENT → WAITING_FOR_CAPACITY
WAITING_FOR_CAPACITY → SENT_TO_RESTAURANT
ANY → EXPIRED

Forbidden Transitions
SENT_TO_RESTAURANT → PENDING
SENT_TO_RESTAURANT → WAITING
EXPIRED → ANY


These are enforced via:

Conditional expressions

Explicit status checks

No downgrade paths

6. Capacity Safety Under Failure

Capacity reservations are:

Atomic

Window-scoped

Time-limited (TTL)

Failure scenarios:

Failure	Outcome
Lambda crash before update	No reservation
Crash after reservation	Order retry detects state
Duplicate call	Condition blocks
TTL expiry	Capacity auto-released
7. Observability & Debuggability

Each failure path logs:

Order ID

Restaurant ID

Capacity window

Error type

Stack trace (for 5xx)

This enables:

Fast root cause analysis

Deterministic replay

Safe production debugging

8. Client Expectations

Clients should:

Retry idempotent endpoints (/vicinity)

Treat 409 as terminal

Never retry order creation blindly

Display WAITING_FOR_CAPACITY honestly

Summary

Arrive is designed to fail safely.
Retries converge. States never regress. Capacity is never overbooked.

This section defines the correctness contract of the system under stress.
