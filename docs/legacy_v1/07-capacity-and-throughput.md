his section documents how Arrive controls restaurant load, why this mechanism exists, and how it guarantees a predictable customer experience without requiring restaurant acknowledgements.

This is a core design pillar of the system.

1. Problem Statement
The Naive Approach (What Fails)

Most early-stage food systems do one of the following:

Fire orders immediately

Queue orders FIFO

Ask restaurants to “accept” or “acknowledge” orders

These approaches break down because:

Restaurants are human-operated systems

Prep speed varies by time, staff, and menu mix

Acknowledgement adds operational overhead

Queues grow invisibly and unpredictably

Customers wait without accurate expectations

Arrive’s Goal

Send orders only when the restaurant has real capacity to handle them — without interrupting restaurant workflows.

2. Core Insight: Capacity > Acknowledgement

Instead of asking:

“Did the restaurant accept the order?”

Arrive asks:

“Does the restaurant have capacity right now to absorb this work?”

This flips the model from reactive confirmation to predictive control.

3. Prep Units: The Load Abstraction
What Is a Prep Unit?

A prep unit is a normalized measure of kitchen effort.

Example:

Item	Prep Units
Coffee	1
Sandwich	2
Burger	3
Large catering tray	8

Each order computes:

prep_units_total = Σ(item.prep_units × qty)


This lets the system reason about load, not just order count.

4. Capacity Windows
Definition

A capacity window is a fixed-duration time slice during which a restaurant can handle a maximum amount of prep work.

Defaults (configurable per restaurant):

capacity_window_seconds = 600   # 10 minutes
max_prep_units_per_window = 20

Window Alignment

Windows are aligned to wall-clock boundaries:

window_start = now - (now % window_seconds)


This guarantees:

Deterministic keys

Predictable behavior

Easy aggregation

5. Atomic Capacity Reservation
Why Atomicity Matters

Multiple customers may arrive at the same time.

Without atomic control:

Capacity would be overbooked

Restaurants would be overwhelmed

Guarantees would collapse

Reservation Logic

When a customer signals vicinity=true, Arrive attempts to reserve capacity:

used_units + order_units <= max_units


This happens via a single conditional update in DynamoDB.

If the condition passes:

Capacity is reserved

Order transitions to SENT_TO_RESTAURANT

If it fails:

No capacity is consumed

Order transitions to WAITING_FOR_CAPACITY

Safety Guarantees

No overbooking

No race conditions

No double reservation

Idempotent retries

6. Order State Outcomes
When Capacity Exists
PENDING_NOT_SENT → SENT_TO_RESTAURANT


Effects:

Order becomes visible to restaurant

Capacity is reserved

Customer can confidently proceed

When Capacity Is Full
PENDING_NOT_SENT → WAITING_FOR_CAPACITY


Customer receives:

{
  "status": "WAITING_FOR_CAPACITY",
  "suggested_start_at": 1768018800,
  "retry_after_seconds": 503,
  "message": "Restaurant is at capacity. Start later to avoid waiting."
}


This is honest backpressure, not a hidden queue.

7. Why We Don’t Require Restaurant Acknowledgement
Operational Reality

Restaurant staff:

Do not want extra taps

Miss notifications during rushes

Already have POS + tickets

Acknowledgements:

Add friction

Fail silently

Don’t reflect actual prep reality

Industry Pattern

Large platforms (e.g. Uber Eats, DoorDash):

Do not block customer flow on acknowledgement

Use heuristics, timing models, and load signals

Optimize for probabilistic correctness

Arrive improves on this by adding hard capacity guarantees.

8. Failure Modes & Behavior
Scenario	Outcome
Duplicate vicinity call	Idempotent
Lambda retry	Safe
Capacity table missing	Treated as empty
Config missing	Defaults applied
Partial failures	Order state preserved
Customer retries	No overbooking
9. Why This Scales

This model:

Requires no restaurant action

Works with any POS

Scales horizontally

Is easy to tune per restaurant

Can evolve into ML-based forecasting

10. Future Extensions

Planned enhancements:

Dynamic prep unit adjustment

Time-of-day capacity curves

Menu-based load weighting

Predictive pre-reservation

Soft capacity borrowing

Restaurant-side visibility tools

Summary

Arrive controls load, not people.
Capacity is enforced before work is created.
Customers get honest timing, restaurants stay sane.

This section defines the behavioral contract between customer, system, and restaurant.
