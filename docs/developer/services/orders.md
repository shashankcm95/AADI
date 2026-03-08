# Orders Service

The orders service is the operational core of the Arrive platform. It manages the full lifecycle of a customer order, from creation through dispatch, preparation, fulfillment, and completion. The service is deliberately the most complex in the system because it coordinates several concurrent concerns: capacity gating, real-time location tracking, geofence-based arrival detection, and a strict state machine that prevents illegal transitions.

All source code lives under `services/orders/src/`.


## Architecture Overview

The orders service runs as a single AWS Lambda function behind an HTTP API Gateway.
Three additional Lambda functions handle asynchronous work: order expiry (scheduled via
EventBridge), geofence events (EventBridge-triggered from AWS Location), and the capacity
system operates through DynamoDB atomic counters rather than a separate service.

The data model centers on a single DynamoDB table (`OrdersTable`) with multiple GSIs:

- **GSI_CustomerOrders**: Keyed on `customer_id` for listing a customer's orders.
- **GSI_RestaurantStatus**: Keyed on `(restaurant_id, status)` for filtering restaurant orders by status.
- **GSI_RestaurantCreated**: Keyed on `(restaurant_id, created_at)` for recency-sorted restaurant order views.
- **GSI_StatusExpiry**: Keyed on `(status, expires_at)` for the expiry Lambda to find stale orders.

Supporting tables include CapacityTable (time-windowed slot tracking), IdempotencyTable (deduplication of order creation), and GeofenceEventsTable (deduplication of EventBridge geofence entries).

The service is organized around a clean separation of concerns:

- **app.py** -- Thin router. Extracts the route key, authenticates the caller, and dispatches to the correct handler. Contains no business logic.
- **handlers/customer.py** -- Seven customer-facing handlers covering order creation, retrieval, listing, location ingestion, vicinity updates, leave advisories, and cancellation.
- **handlers/restaurant.py** -- Three restaurant-facing handlers for listing orders, acknowledging receipt, and updating order status.
- **engine.py** -- Pure decision logic. Every state transition is computed here as an `UpdatePlan` dataclass, which the handler then applies to DynamoDB. The engine never touches the database directly.
- **capacity.py** -- Time-windowed capacity reservation using DynamoDB atomic counters.
- **location_bridge.py** -- Publishes device positions to AWS Location Service for geofence evaluation.
- **models.py** -- Status enums, Session and Resource dataclasses, and DynamoDB deserialization.
- **db.py** -- Shared imports hub. All DynamoDB table references and re-exported shared-layer functions live here so handler modules have a single import target.
- **errors.py** -- Custom exception hierarchy (ValidationError, NotFoundError, InvalidStateError, ExpiredError).
- **expire_orders.py** -- Scheduled Lambda that marks abandoned orders as EXPIRED.
- **geofence_events.py** -- EventBridge consumer that processes AWS Location geofence ENTER events.


## Router and Access Control

The router in `app.py` uses API Gateway's `routeKey` field (e.g., `POST /v1/orders`) for dispatch. Routes are partitioned into two sets: CUSTOMER_ROUTES and RESTAURANT_ROUTES.

Customer routes require the caller to have a `customer_id` (the Cognito `sub` claim). The role check allows explicit `customer` role, but also accepts users with no role and no restaurant assignment. This fallback exists because legacy and federated users may not carry the `custom:role` attribute, and treating them as customers by default provides a seamless onboarding experience without requiring Cognito attribute migration.

Restaurant routes require `admin` or `restaurant_admin` role. For `restaurant_admin` users, the router verifies that the `restaurant_id` in the URL path matches the restaurant bound to their Cognito account. This prevents a restaurant admin from accessing another restaurant's orders, even if they somehow craft the request.

Error handling at the router level maps custom exceptions to HTTP status codes: NotFoundError to 404, InvalidStateError and ExpiredError to 409, ValidationError to 400. Any unhandled exception returns a generic 500. Every request is wrapped in a Timer context manager that logs the total duration in milliseconds.


## The Dispatch Engine

The engine (`engine.py`) is the decision-making brain of the orders service. It is designed as a collection of pure functions that accept the current session state and return an `UpdatePlan` describing what should change. This separation is intentional: by keeping the engine free of I/O, it becomes trivially testable and its behavior is fully deterministic.

### UpdatePlan

The `UpdatePlan` is a frozen dataclass with three fields: `condition_allowed_statuses` (a tuple of statuses that DynamoDB must verify before applying the update), `set_fields` (a dict of fields to SET), and `remove_fields` (a tuple of fields to REMOVE). The handler translates this plan into a DynamoDB `update_item` call with the appropriate condition expression.

The condition check is critical. It implements optimistic concurrency control: if two concurrent requests both read the same order and decide to transition it, only one will succeed because the DynamoDB condition will fail for the second writer. The handler detects this (`ConditionalCheckFailedException`) and either returns the fresh state or rolls back the capacity reservation.

### State Machine

The `ALLOWED_TRANSITIONS` dictionary defines the legal progression:

```
SENT_TO_DESTINATION -> IN_PROGRESS -> READY -> FULFILLING -> COMPLETED
```

This is a strict linear chain. There are no skip-ahead transitions and no backward transitions. The engine also enforces idempotency: if the current status already equals the requested status, the engine returns a no-op plan with no condition check or field mutations.

Status transitions outside this chain (like PENDING to SENT, or PENDING to WAITING) are handled by the dispatch logic in `decide_vicinity_update()` and `decide_arrival_update()` rather than the generic status update path.

### Dispatch Decisions

The `decide_vicinity_update()` function handles the moment a customer enters a restaurant's zone. If the customer reports `vicinity=True` and the order is PENDING or WAITING, the function checks whether a capacity slot was reserved. If reserved, the order transitions to SENT_TO_DESTINATION with a SOFT receipt mode. If capacity is exhausted, the order transitions to WAITING_FOR_CAPACITY with a `suggested_start_at` timestamp indicating when the next capacity window opens.

The `decide_arrival_update()` function handles progressive arrival events (5_MIN_OUT, PARKING, AT_DOOR, EXIT_VICINITY). For the first three, if the order is still PENDING or WAITING and `allow_dispatch_transition` is True, the engine force-sends the order. The rationale is simple: if a customer is physically at the door, the restaurant needs to know regardless of whether the customer pressed any button. For EXIT_VICINITY, if the order is in FULFILLING status, the engine auto-completes it with a condition guard to prevent race conditions.

### Cancellation

Orders can only be cancelled while in PENDING_NOT_SENT or WAITING_FOR_CAPACITY status.
Once an order is SENT, the restaurant has begun acting on it, and cancellation would
create coordination problems. The `decide_cancel()` function raises InvalidStateError
for any other status, which the router maps to HTTP 409.

The cancel plan includes `remove_fields` for `waiting_since` and `suggested_start_at`,
cleaning up scheduling metadata that is no longer relevant once the order is cancelled.
The handler then calls `db.release_capacity_slot(session)` to free any reserved capacity.

### Validation

The engine provides `validate_resources_payload()` for order creation. It enforces:

- At least one item in the order.
- Each item must have an `id` (or legacy `menu_item_id`) and a `qty`.
- Quantity must be between 1 and 99 (`MAX_ITEM_QTY`). The upper bound prevents absurd
  orders that could overflow totals or overwhelm the kitchen.

### Session Model Construction

The `create_session_model()` function builds the initial order record. It computes
`total_cents` by summing `price_cents * qty` across all items, computes `work_units`
by summing `work_units * qty` (falling back to legacy `prep_units`), and calculates
the Arrive platform fee at 2% of the total (split evenly between restaurant and customer).

The model starts in `PENDING_NOT_SENT` status with `arrival_status: None`, a 1-hour
expiry (`expires_at = now + 3600`), and a 90-day DynamoDB TTL for eventual cleanup.
The `receipt_mode` defaults to SOFT and `payment_mode` defaults to PAY_AT_RESTAURANT,
reflecting the current product scope.


## Capacity Reservation

The capacity system (`capacity.py`) manages how many orders a restaurant can accept concurrently within a time window. The design uses fixed 300-second (5-minute) windows, keyed by `(restaurant_id, window_start)` in a DynamoDB table.

### Why Fixed Windows

Fixed windows were chosen over sliding windows for two reasons. First, DynamoDB atomic counters need a stable key, and a sliding window would require continuously creating new rows. Second, 5-minute windows provide sufficient granularity for restaurant operations without creating excessive DynamoDB items. Each window row has a TTL set to `window_start + window_seconds + 3600`, so rows are automatically cleaned up an hour after the window closes.

### Atomic Reservation

The `try_reserve_slot()` function uses a DynamoDB conditional update: it atomically increments `current_count` only if the current value is less than `max_concurrent`. If the item does not exist, `if_not_exists` initializes it to zero. This is thread-safe and works correctly even under high concurrency because DynamoDB serializes writes to the same item.

### Release on Completion or Cancel

When an order is completed or cancelled, the handler calls `release_slot()` to decrement the counter with a floor at zero. The release is best-effort: if the DynamoDB row has already been removed by TTL, the operation silently no-ops. This prevents negative counts while ensuring capacity is freed for other customers.

### Leave Advisory

The `estimate_leave_advisory()` function provides customers with a non-binding estimate of when to leave for the restaurant. It reads the current window's usage and the restaurant's max capacity, then recommends either LEAVE_NOW (if slots are available) or WAIT (with an estimated wait in seconds). This endpoint never reserves capacity and explicitly notes in the response that it is advisory only.


## Location Ingestion Pipeline

The `ingest_location` handler in `handlers/customer.py` accepts GPS coordinates from the mobile app and performs two actions: it stores the latest position on the order record in DynamoDB, and it publishes the position to AWS Location Service via `location_bridge.py`.

### Input Coercion

The location bridge includes two defensive coercion functions. `coerce_finite_float()` rejects NaN, Infinity, and non-numeric values, returning None instead of allowing corrupt coordinates to propagate. `coerce_epoch_seconds()` handles the common mobile-SDK ambiguity between seconds and milliseconds by checking if the timestamp exceeds 10 billion (which would be year 2286 in seconds but only 2001 in milliseconds) and dividing accordingly.

### Same-Location Bootstrap

A subtle edge case occurs when a customer creates an order while already inside the restaurant. The geofence ENTER event will never fire because the customer never crossed the boundary. The `_maybe_bootstrap_same_location_arrival()` function addresses this by computing the haversine distance between the customer's GPS position and the restaurant's coordinates. If the distance is within a configurable radius (default 35 meters), it synthesizes an AT_DOOR event to dispatch the order immediately. Without this bootstrap, orders placed on-site would remain stuck in PENDING until they expire.

### Vicinity Event Suppression

The `_should_suppress_vicinity_event()` function prevents noisy or stale arrival
events from causing unnecessary database writes. It implements three suppression rules:

1. **Arrival regression**: If the current arrival status has higher priority than the
   incoming event (e.g., AT_DOOR has priority 3, 5_MIN_OUT has priority 1), the incoming
   event is suppressed. A customer who has been detected at the door should not regress
   to "5 minutes out" due to GPS drift.

2. **Duplicate after dispatch**: If the incoming event matches the current arrival status
   and the order is no longer in PENDING or WAITING, the event is suppressed. Once the
   order has been sent to the restaurant, repeating the same arrival signal adds no value.

3. **Cooldown within dispatch-eligible states**: If the order is still PENDING or WAITING
   and the same event arrives within 8 seconds of the last update, it is suppressed. This
   prevents hot-loop hammering from a mobile client that is rapidly retrying, while still
   allowing periodic retries to pick up newly freed capacity.

Each suppression case returns a reason string that is included in the response body,
allowing the mobile client to understand why its event was not processed.

### Dispatch Trigger Configuration

Restaurants can configure which arrival event triggers dispatch. The default is 5_MIN_OUT
(ZONE_1), but a restaurant that wants customers closer before starting preparation can
set the trigger to PARKING (ZONE_2) or AT_DOOR (ZONE_3). The `update_vicinity` handler
reads this configuration and compares the incoming event's priority against the configured
trigger priority. Events below the threshold are processed as arrival-status-only updates
without attempting capacity reservation.


## Geofence Event Processing

The `geofence_events.py` Lambda is triggered by EventBridge when AWS Location detects that a device has entered a geofence. The geofence ID encodes the restaurant ID and the arrival zone using a pipe delimiter (e.g., `restaurant-uuid|5_MIN_OUT`).

### Idempotency

The handler uses a dedicated `GeofenceEventsTable` with `attribute_not_exists` condition to deduplicate events. EventBridge guarantees at-least-once delivery, so the same geofence entry could arrive multiple times. The deduplication table has a 7-day TTL.

### Shadow Mode

The geofence processor supports a shadow mode controlled by the
`LOCATION_GEOFENCE_CUTOVER_ENABLED` environment variable. In shadow mode, the handler
records the geofence event on the order record (as `geofence_shadow_last_event`,
`geofence_shadow_last_event_id`, and `geofence_shadow_last_received_at`) but does not
trigger any status transition.

This shadow recording exists to validate geofence accuracy against the existing
client-side arrival detection before cutting over. By comparing shadow events with
client-reported arrival events, the team can verify that geofence zones fire at the
correct distances and with acceptable latency.

The `LOCATION_GEOFENCE_FORCE_SHADOW` variable provides an additional override to keep
shadow mode active even when cutover is enabled. This is useful during a rollback:
if cutover reveals problems, flipping `FORCE_SHADOW` to true immediately returns to
shadow-only mode without redeploying.

### Candidate Order Lookup

The geofence event contains a device ID (the customer's Cognito sub) and a geofence ID
(encoding the restaurant and zone). The handler needs to find the customer's active
order for that restaurant. It queries `GSI_CustomerOrders` for the customer's most recent
25 orders and filters for the matching restaurant_id and an active status. This approach
avoids creating a dedicated GSI for the (customer_id, restaurant_id) compound key, which
would add cost for a relatively infrequent query pattern.


## Order Expiry

The `expire_orders.py` Lambda runs on a schedule (typically every few minutes via EventBridge). It queries the `GSI_StatusExpiry` index for orders in PENDING_NOT_SENT or WAITING_FOR_CAPACITY status whose `expires_at` timestamp has passed, then transitions them to EXPIRED using a conditional update.

The expiry Lambda includes several safety mechanisms. It limits each run to 500 items (`MAX_ITEMS_PER_RUN`) and checks remaining Lambda execution time against a 2-second buffer (`REMAINING_MS_BUFFER`) to avoid timeout-related partial processing. If the GSI is unavailable (e.g., during a deployment), the handler falls back to a table scan with the same filter expression, controlled by the `EXPIRY_SCAN_FALLBACK_ENABLED` environment variable.

Each individual expiry update uses a condition expression to verify the order's current status has not changed since it was read. This prevents the expiry Lambda from overwriting a status that was legitimately updated between the query and the write.


## Handler Structure

Customer handlers follow a consistent pattern: authenticate, parse input, load the session from DynamoDB, call the engine for a decision, apply the resulting UpdatePlan, and return the response. All handlers bind structured logging context (order_id, customer_id, restaurant_id) so that every log line can be correlated.

The `create_order` handler includes idempotency protection via an `Idempotency-Key` header. If the key is present, the handler attempts to lock it in the IdempotencyTable with `attribute_not_exists`. If the key already exists and is COMPLETED, the stored response is returned. If the key exists but is still PROCESSING, a 409 is returned. On failure, the lock is deleted to allow retries. This prevents duplicate orders from network retries or double-taps.

Restaurant handlers (`list_restaurant_orders`, `ack_order`, `update_order_status`) use
GSIs keyed by restaurant_id for efficient queries. The list handler supports two query
modes: when a `status` filter is provided, it uses `GSI_RestaurantStatus` for exact
status matching; when no filter is provided, it uses `GSI_RestaurantCreated` with
`ScanIndexForward=False` to return orders in reverse chronological order, which is the
natural view for an operator dashboard.

The acknowledgment handler upgrades an order's receipt mode from SOFT to HARD, indicating
the restaurant has explicitly confirmed receipt. This distinction matters for the
auto-complete logic: only SOFT-receipt orders can be auto-completed on EXIT_VICINITY,
because HARD-receipt orders imply the restaurant is actively tracking the customer.
The ack handler is idempotent: if the receipt mode is already HARD, it returns a no-op
response without writing to DynamoDB.

The status update handler enforces destination ownership through the engine's
`decide_destination_status_update()` function, which verifies that the restaurant_id
in the request matches the order's destination. Each status transition records a semantic
timestamp (`started_at`, `ready_at`, `fulfilling_at`, `completed_at`) that enables
preparation-time analytics. When an order reaches COMPLETED, the handler releases the
capacity slot.

### Pagination

Both customer and restaurant listing handlers support cursor-based pagination using
DynamoDB's `LastEvaluatedKey`. The cursor is base64-encoded JSON, opaque to the client.
The maximum page size is capped at 100 items to prevent excessive read throughput. If
a `next_token` cannot be decoded, the handler returns 400 rather than silently falling
back to an unpaginated query.


## Error Handling

The service defines four custom exceptions in `errors.py`, each carrying a `code`, `http_status`, and `message`. The router maps these to HTTP responses:

- **ValidationError** (400): Invalid input such as missing required fields, out-of-range quantities, or unsupported payment modes.
- **NotFoundError** (404): Order does not exist, or the authenticated customer does not own the order. Both cases return 404 to avoid leaking existence information.
- **InvalidStateError** (409): Attempted state transition is not allowed by the state machine.
- **ExpiredError** (409): Order has passed its `expires_at` timestamp.

All unhandled exceptions are caught at the router level, logged with full stack trace via `exc_info=True`, and returned as a generic 500 to avoid leaking internal details.
