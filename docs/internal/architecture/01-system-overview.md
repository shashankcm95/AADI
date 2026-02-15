```markdown
01 — System Overview

Purpose of the System

Arrive is a proximity-aware, capacity-gated order intake system for restaurants.

Its core goal is to:

- Accept customer orders
- Delay sending them to the restaurant until it is operationally safe
- Prevent kitchen overload using explicit capacity windows
- Provide customers with predictable, honest timing signals

This system intentionally avoids:

- Hard real-time guarantees
- Manual restaurant acknowledgements in the critical path
- Complex queue orchestration in early stages

Instead, it uses deterministic heuristics + atomic capacity reservation to achieve reliability with minimal restaurant burden.

**High-Level Architecture**

At a high level, Arrive consists of:

```
Client
  |
  |  HTTP (REST)
  v
API Gateway
  |
  v
AWS Lambda (OrdersFunction)
  |
  +--> DynamoDB (Orders Table)
  |
  +--> DynamoDB (Restaurant Config Table)
  |
  +--> DynamoDB (Capacity Table)
```

**Key Design Principles**

- Stateless compute (Lambda)
- Stateful decisions in DynamoDB
- Idempotent transitions
- Atomic capacity enforcement
- Time-windowed load control

**Core Concepts**

1. **Order as a State Machine**

   An order moves through a strict, well-defined lifecycle.

   Orders are not pushed to restaurants immediately. Instead, they are:

   - Created optimistically
   - Activated based on customer proximity
   - Gated by kitchen capacity

   This allows the system to remain flexible and predictive without overwhelming kitchens.

2. **Capacity Windows**

   Capacity is enforced using fixed-duration time windows.

   Each restaurant defines:

   - `capacity_window_seconds` (default: 600s / 10 minutes)
   - `max_prep_units_per_window`

   Orders consume prep units. Prep units are atomically reserved per window.

   This guarantees:

   - No overbooking
   - No race conditions
   - Predictable throughput

3. **Proximity (Vicinity)**

   The system does not assume customer arrival. Instead:

   - Customers explicitly signal proximity via `/vicinity`
   - Only then does the system attempt to send the order
   - Capacity is checked at that moment

   This avoids:

   - Premature kitchen load
   - Orders piling up when customers are delayed
   - Ghost orders from abandoned sessions

**Data Stores and Responsibilities**

- **Orders Table (Primary System of Record)**

  Stores:

  - Order metadata
  - Items and prep units
  - Lifecycle state
  - Timestamps for transitions

  This table defines what the system believes is true.

- **Restaurant Config Table**

  Stores:

  - Capacity configuration
  - Window size
  - Prep unit limits

  This table allows:

  - Per-restaurant tuning
  - Operational flexibility
  - Future overrides without code changes

- **Capacity Table**

  Stores:

  - Used prep units per `(restaurant_id, window_start)`
  - TTL-based cleanup

  This table enforces hard safety guarantees:

  - Atomic updates
  - No double booking
  - No oversubscription

**Request Flow (Happy Path)**

1. **Order Creation**
   - `POST /v1/orders`

   Order is created as `PENDING_NOT_SENT`. No capacity is reserved. Restaurant is not notified.

2. **Customer Signals Vicinity**
   - `POST /v1/orders/{order_id}/vicinity`

   System performs:

   - Order validation
   - Expiry check
   - Capacity window calculation
   - Atomic capacity reservation attempt

3a. **Capacity Available**

   If reservation succeeds:

   - Order transitions to `SENT_TO_DESTINATION`
   - `sent_at` and `capacity_window_start` recorded
   - Order appears in restaurant queue

3b. **Capacity Full**

   If reservation fails:

   - Order transitions to `WAITING_FOR_CAPACITY`
   - Suggested retry time returned
   - Customer receives clear guidance

**Failure Handling Philosophy**

The system is designed so that:

- Failures fail safe
- Restaurants are never overloaded
- Customers receive consistent responses

Key behaviors:

- Conditional updates prevent double transitions
- Capacity reservation is atomic
- All state is queryable and inspectable

**Explicit Non-Goals (for Now)**

This system intentionally does not:

- Require restaurant acknowledgements
- Guarantee preparation start times
- Support partial order fulfillment
- Handle refunds or payments
- Handle kitchen-side rejections

These are future layers, not missing features.

**Why This Architecture Works**

- Scales linearly with traffic
- Protects restaurants by design
- Keeps customer expectations honest
- Avoids complex distributed coordination
- Is easy to reason about under failure

**What Comes Next**

Next documentation sections will define:

- Repository structure
- Order state machine in detail
- API contracts and examples
- Capacity math and guarantees
- Future extension points

**Version:** 2.1
**Date:** 2026-02-12
```