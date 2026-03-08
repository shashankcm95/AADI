# Order Lifecycle

The order lifecycle is the heart of the Arrive platform. Every order follows a deterministic state machine from creation to completion, governed by capacity constraints, arrival events, and restaurant actions. This document describes every state, every transition, the dispatch engine that drives them, and the supporting systems for capacity, arrival tracking, and expiry.

## The State Machine

An order progresses through a linear pipeline of statuses. The primary happy path is:

```
PENDING_NOT_SENT
       |
       | (customer enters vicinity + capacity available)
       v
SENT_TO_DESTINATION
       |
       | (restaurant starts preparation)
       v
  IN_PROGRESS
       |
       | (food is ready)
       v
     READY
       |
       | (food is being served to the table)
       v
   FULFILLING
       |
       | (order handed off)
       v
   COMPLETED
```

Two alternative terminal states exist:

```
PENDING_NOT_SENT -----> CANCELED     (customer cancels before dispatch)
WAITING_FOR_CAPACITY -> CANCELED     (customer cancels while waiting)
PENDING_NOT_SENT -----> EXPIRED      (TTL elapsed without dispatch)
WAITING_FOR_CAPACITY -> EXPIRED      (TTL elapsed while waiting)
```

And one intermediate holding state:

```
PENDING_NOT_SENT -----> WAITING_FOR_CAPACITY  (vicinity reached but no capacity)
WAITING_FOR_CAPACITY -> SENT_TO_DESTINATION   (capacity becomes available)
```

Here is the complete state diagram:

```
                         +-------------------+
                         | PENDING_NOT_SENT  |
                         +--------+----------+
                                  |
                    +-------------+-------------+
                    |                           |
            vicinity=true                  TTL elapsed
            capacity available             or cancel
                    |                           |
                    v                           v
     +-----------------------------+    +-----------+
     |    SENT_TO_DESTINATION      |    |  EXPIRED  |
     +-------------+---------------+    +-----------+
                   |                    +-----------+
                   |                    | CANCELED  |
                   v                    +-----------+
            +------+-------+                 ^
            | IN_PROGRESS  |                 |
            +------+-------+          (cancel from
                   |               PENDING or WAITING)
                   v
            +------+-------+
            |    READY     |
            +------+-------+
                   |
                   v
            +------+-------+
            |  FULFILLING  |
            +------+-------+
                   |
                   v
            +------+-------+
            |  COMPLETED   |
            +--------------+

     PENDING_NOT_SENT -----> WAITING_FOR_CAPACITY
     (vicinity=true,          (vicinity=true,
      no capacity)             capacity later available)
           |                         |
           +------> EXPIRED <--------+
```

## Status Definitions

**PENDING_NOT_SENT** is the initial status of every order. The order has been created and validated, but the customer has not yet arrived in the restaurant's vicinity. The restaurant does not see this order on their dashboard. The order has a TTL (expiry timestamp); if the customer does not arrive before expiry, the order transitions to EXPIRED.

**WAITING_FOR_CAPACITY** means the customer has arrived in the vicinity, but the restaurant's current capacity window is full. The order is queued. When capacity opens up (the current window's slot count drops below the maximum, or the next window starts), the order transitions to SENT_TO_DESTINATION. While waiting, the response includes a `suggested_start_at` timestamp indicating the next capacity window boundary.

**SENT_TO_DESTINATION** means the order has been dispatched to the restaurant. The restaurant sees it on their dashboard and can begin preparation. This is the first status where the restaurant is aware of the order. The order arrives with a default receipt mode of SOFT unless the restaurant explicitly acknowledges it (upgrading to HARD).

**IN_PROGRESS** means the restaurant has started preparing the order. This transition is initiated by the restaurant through the status update endpoint.

**READY** means the food is prepared and ready to be served. The restaurant sets this status when the order is ready to be brought to the customer's table.

**FULFILLING** means the food is being served to the customer's table. This is the last active status before completion.

**COMPLETED** is the terminal success state. The order has been fully served. In SOFT receipt mode, this can happen automatically when the customer exits the vicinity. In HARD mode, the restaurant must explicitly complete the order.

**CANCELED** is a terminal state for orders that were canceled before dispatch. Only orders in PENDING_NOT_SENT or WAITING_FOR_CAPACITY can be canceled. Once an order has been sent to the restaurant, cancellation is no longer possible through the API.

**EXPIRED** is a terminal state for orders whose TTL elapsed before dispatch. A scheduled Lambda function runs every 5 minutes, queries the `GSI_StatusExpiry` index for PENDING_NOT_SENT and WAITING_FOR_CAPACITY orders with `expires_at` in the past, and transitions them to EXPIRED using conditional writes.

## Allowed Transitions

The engine enforces strict transition rules. The allowed transitions for restaurant-initiated status updates are:

```
SENT_TO_DESTINATION  -->  IN_PROGRESS
IN_PROGRESS          -->  READY
READY                -->  FULFILLING
FULFILLING           -->  COMPLETED
```

Skipping states is not permitted. A restaurant cannot move an order directly from SENT_TO_DESTINATION to READY. Each step must be taken in sequence.

Transitions are idempotent: if the order is already in the requested status, the update succeeds and returns the current state without modifying anything. This prevents errors from duplicate requests.

All status updates use DynamoDB conditional writes. The update expression includes a condition that the current status matches the expected "from" status. If another process has already changed the status (a race condition), the conditional write fails and the handler returns a 409 Conflict.

## The Dispatch Engine

The dispatch engine is the pure-logic core of the orders service, implemented in `services/orders/src/engine.py`. It contains no I/O operations -- no DynamoDB calls, no network requests. Instead, it takes the current order state as input and returns an `UpdatePlan` data structure that describes what changes should be applied to storage.

This design separates decision-making from side effects. The engine decides; the handler applies. This makes the engine fully testable with simple unit tests that pass in dictionaries and assert on the returned plan.

The `UpdatePlan` dataclass contains:
- `condition_allowed_statuses`: a tuple of statuses that the order must currently be in for the update to proceed (used as a DynamoDB condition expression)
- `set_fields`: a dictionary of fields to set on the order
- `remove_fields`: a tuple of field names to remove from the order
- `response`: the response body to return to the caller

### Vicinity Update Decision

When the mobile app reports `vicinity=true`, the `decide_vicinity_update` function evaluates the situation:

1. If `vicinity` is not `true`, no action is taken.
2. If the order is not in PENDING_NOT_SENT or WAITING_FOR_CAPACITY, no action is taken.
3. If capacity has been reserved, the order transitions to SENT_TO_DESTINATION with the capacity window recorded.
4. If capacity is full, the order transitions to WAITING_FOR_CAPACITY with a `suggested_start_at` timestamp.

### Arrival Event Decision

The `decide_arrival_update` function handles progressive arrival events (5_MIN_OUT, PARKING, AT_DOOR, EXIT_VICINITY):

For 5_MIN_OUT, PARKING, and AT_DOOR: if the order is still in PENDING_NOT_SENT or WAITING_FOR_CAPACITY and dispatch transitions are allowed, the order is force-sent to the restaurant. The rationale is that if the customer is parking or at the door, the restaurant needs to know immediately regardless of the original dispatch trigger configuration.

For EXIT_VICINITY: if the order is in FULFILLING status, it is automatically completed. This only happens when the receipt mode is SOFT. A condition guard ensures that concurrent transitions do not conflict.

### Cancel Decision

The `decide_cancel` function allows cancellation only from PENDING_NOT_SENT or WAITING_FOR_CAPACITY. The update plan includes a condition on these statuses to prevent races with dispatch.

### Acknowledgment Decision

The `decide_ack_upgrade` function handles the restaurant acknowledging an order. If the order is in SENT_TO_DESTINATION status and currently in SOFT receipt mode, it upgrades to HARD receipt mode. If already HARD, the operation is a no-op.

## Capacity System

The capacity system prevents restaurants from being overwhelmed by limiting the number of concurrent orders within fixed time windows.

**Time Windows** are 300 seconds (5 minutes) by default. The current window is computed by flooring the current epoch timestamp to the nearest 300-second boundary. For example, timestamp 1700000150 falls in the window starting at 1700000000.

**Slot Reservation** uses DynamoDB atomic counters. The `CapacityTable` has a composite key of `(restaurant_id, window_start)`. When an order is dispatched, the system performs an atomic increment with a condition: `current_count < max_concurrent_orders OR attribute_not_exists(current_count)`. If the condition fails, the restaurant is at capacity.

**Slot Release** happens when an order is completed or canceled. The handler decrements the `current_count` with a floor at zero. If the capacity row has already been expired by TTL, the release is a safe no-op.

**Configuration** is per-restaurant, stored in the `RestaurantConfigTable`. Each restaurant can configure:
- `max_concurrent_orders` (default: 10)
- `capacity_window_seconds` (default: 300)
- `dispatch_trigger_event` (default: `5_MIN_OUT`, also accepts `PARKING` or `AT_DOOR`)

The leave advisory endpoint (`GET /v1/orders/{order_id}/advisory`) provides a non-binding capacity estimate. It reads the current window usage without reserving a slot, then recommends either `LEAVE_NOW` (slots available) or `WAIT` (at capacity, try again at `suggested_leave_at`).

## Arrival Tracking Pipeline

Arrival tracking connects the customer's physical location to the order state machine. It operates through two parallel channels:

### Client-Reported Vicinity

The mobile app monitors the device's GPS position and determines when the customer is near the restaurant. When the customer enters the vicinity zone, the app sends a `POST /v1/orders/{order_id}/vicinity` request with `vicinity: true` and an arrival event type. This is the primary dispatch mechanism.

The client also sends periodic location updates via `POST /v1/orders/{order_id}/location`, which publishes positions to the Amazon Location Service tracker. These positions feed into the geofence evaluation pipeline.

### Geofence-Based Arrival

Amazon Location Service evaluates device positions against restaurant geofence zones. When a device enters a geofence, EventBridge delivers an ENTER event to the `GeofenceEventsFunction`. This function:

1. Deduplicates the event using the `GeofenceEventsTable` (conditional put with `attribute_not_exists`).
2. Parses the geofence ID to extract the restaurant ID and arrival event name.
3. Finds the customer's active order for that restaurant.
4. In shadow mode (default): records the event as metadata on the order without triggering any status transition.
5. In cutover mode: invokes the same vicinity update handler that the client uses, effectively replacing client-reported vicinity with server-evaluated geofence events.

The shadow/cutover toggle is controlled by two environment variables:
- `LOCATION_GEOFENCE_CUTOVER_ENABLED`: when `true`, geofence events trigger real status transitions.
- `LOCATION_GEOFENCE_FORCE_SHADOW`: when `true`, overrides cutover and forces shadow mode. This is an emergency rollback switch.

Three geofence zones per restaurant correspond to arrival events:
- Vicinity zone (farthest): triggers `5_MIN_OUT`
- Nearby zone (medium): triggers `PARKING`
- Arrive zone (closest): triggers `AT_DOOR`

## Receipt Modes

Receipt modes control how an order is completed.

**SOFT** (default) means the order can be auto-completed. When the customer exits the vicinity (EXIT_VICINITY event) while the order is in FULFILLING status, the system automatically transitions it to COMPLETED. This is the hands-free experience: the customer finishes their meal and leaves, and the order closes itself.

**HARD** means the order requires explicit completion. The restaurant must manually advance the order to COMPLETED. SOFT-to-HARD upgrade happens when the restaurant acknowledges the order via the `ack` endpoint. Once an order is in HARD mode, EXIT_VICINITY events do not trigger auto-completion.

The default is SOFT because Arrive's core value proposition is frictionless, GPS-driven order management. HARD mode exists for restaurants that need explicit confirmation that the food has been served, such as those with complex table service flows.

## Idempotency

Order creation supports idempotency via the `Idempotency-Key` header. The client (typically the mobile app) generates a UUID and includes it with the create order request. The system checks the `IdempotencyTable` for an existing entry:

- If the key does not exist, a new entry is created with a TTL and the order is created normally.
- If the key already exists, the original order is returned without creating a duplicate.

This protects against double-taps, network retries, and mobile connectivity issues where a request succeeds on the server but the response is lost.

## Order Expiry

A scheduled Lambda function (`expire_orders.py`) runs every 5 minutes via an EventBridge rule. It queries the `GSI_StatusExpiry` index for orders in PENDING_NOT_SENT or WAITING_FOR_CAPACITY status whose `expires_at` timestamp is in the past. For each matching order, it transitions the status to EXPIRED using a conditional write.

The conditional write ensures that if the order has been dispatched between the query and the update (a race), the expiry is silently skipped rather than overwriting a valid status.

Safety limits prevent the expiry function from running too long or consuming too many DynamoDB resources:
- Maximum 500 items processed per invocation
- Abort when less than 2 seconds remain in the Lambda execution
- 100 items per query page

If the status/expiry GSI is unavailable (during initial deployment or a DynamoDB issue), the function falls back to a full table scan with the same filter criteria. This fallback is controlled by the `EXPIRY_SCAN_FALLBACK_ENABLED` environment variable.

## Platform Fee Calculation

Every order includes an Arrive platform fee, calculated as a percentage of the order total (default 2%). The fee is split evenly between the restaurant and the customer. The `calculate_arrive_fee` function computes:

- `total_fee = round(order_total_cents * fee_percent / 100)`
- `restaurant_fee = total_fee // 2` (integer division)
- `customer_fee = total_fee - restaurant_fee` (remainder goes to customer share)

The fee is recorded on the order at creation time but is informational in the current scope, since all orders use the PAY_AT_RESTAURANT payment mode.

## Item Validation

Items in the order payload are validated by the `validate_resources_payload` function:

- At least one item is required.
- Each item must have an `id` (or legacy `menu_item_id`).
- Each item must have a `qty` between 1 and 99 (MAX_ITEM_QTY).

If validation fails, a `ValidationError` is raised and the handler returns a 400 response.
