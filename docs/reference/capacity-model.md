# Capacity Model

The capacity model controls how many customer orders a restaurant can handle concurrently. It prevents a restaurant from being overwhelmed by a sudden surge of arrivals, ensures customers receive timely service, and provides advisory information to help customers decide when to leave for the restaurant.


## Problem Statement

Without capacity management, a restaurant that normally handles 8 orders at a time could receive 30 arrival signals in the same 5-minute window during a lunch rush. The kitchen would be overwhelmed, wait times would spike, and customer satisfaction would collapse. The capacity model solves this by gating dispatch: orders are only "sent" to the restaurant when a capacity slot is available.


## Fixed Time Windows

Capacity is tracked in fixed time windows. The default window duration is 300 seconds (5 minutes). A window is identified by its start timestamp, computed by flooring the current epoch time to the nearest window boundary:

```
window_start = (now // window_seconds) * window_seconds
```

For example, at epoch time 1007 with a 300-second window, the window start is 900. At epoch time 1200, the window start is 1200.

### Why 300 Seconds

The 5-minute window was chosen to balance two competing concerns:

1. **Granularity**: Shorter windows (e.g., 60 seconds) would create too many DynamoDB items and would be overly sensitive to timing jitter -- a customer who arrives at second 59 of one window and another who arrives at second 1 of the next window would never compete for the same slot, even though they arrive 2 seconds apart.

2. **Responsiveness**: Longer windows (e.g., 30 minutes) would be too coarse. A restaurant with a max of 10 orders per window could accept 10 orders in the first minute and then make everyone wait 29 minutes for the next window.

Five minutes approximates the time it takes for a restaurant to acknowledge, prepare, and begin fulfilling a typical order. It also matches the ZONE_1 (5_MIN_OUT) geofence radius, creating a natural alignment between "customer is 5 minutes away" and "the capacity window the customer will arrive in."

### Window Keying

Each window is stored as a DynamoDB item with a composite key:

- **Partition key** (`restaurant_id`): The restaurant this window belongs to.
- **Sort key** (`window_start`): The epoch timestamp of the window boundary.

This keying allows efficient queries for a specific restaurant's current window and supports multiple restaurants on the same table without contention.


## Atomic Reservation

When a customer's arrival signal triggers dispatch (typically at the 5_MIN_OUT geofence event or when the customer explicitly reports vicinity), the system attempts to reserve a capacity slot using DynamoDB's atomic counter pattern:

```
UpdateExpression: SET current_count = if_not_exists(current_count, 0) + 1, ttl = :ttl
ConditionExpression: attribute_not_exists(current_count) OR current_count < :max_concurrent
```

This operation atomically increments the counter and fails if the restaurant is at capacity. The `if_not_exists` handles the first reservation in a new window, where the item does not yet exist.

### Why Atomic Counters

The atomic counter approach was chosen over alternatives like read-then-write or DynamoDB transactions because:

1. **Single round trip**: One DynamoDB call both checks and reserves. A read-then-write approach would require two calls and would be vulnerable to race conditions without additional locking.
2. **No external coordination**: No distributed locks, no Redis, no SQS. The DynamoDB item itself is the coordination primitive.
3. **Correctness under concurrency**: DynamoDB serializes writes to the same item. If two customers arrive simultaneously, exactly one will succeed and one will be told to wait. There is no window for double-counting.

### TTL Cleanup

Each capacity item has a TTL set to `window_start + window_seconds + 3600`. DynamoDB's TTL mechanism automatically deletes the item roughly one hour after the window closes. This prevents the table from growing indefinitely and eliminates the need for a cleanup job.


## Guided Release

Capacity slots are released in two scenarios:

### Completion

When an order reaches COMPLETED status (either through the restaurant status update flow or auto-completion on EXIT_VICINITY), the handler calls `release_slot()` to decrement the counter. This frees the slot for the next customer.

### Cancellation

When a customer cancels an order that was in WAITING_FOR_CAPACITY or had a reserved slot, the handler releases the capacity. This is important because a cancelled order should not continue to consume capacity.

### Release Mechanics

The release operation decrements `current_count` with a condition that it must be greater than zero:

```
UpdateExpression: SET current_count = current_count - 1
ConditionExpression: current_count > 0
```

If the condition fails (count already zero, or the item has been TTL-deleted), the operation silently no-ops. This prevents negative counts, which would incorrectly inflate available capacity.

### Race Condition Handling

When a vicinity update fails due to a concurrent status change (ConditionalCheckFailedException on the order update), the handler rolls back the capacity reservation. Without this rollback, phantom slots would be consumed: the order was not actually dispatched, but a capacity slot was reserved for it. The rollback is best-effort -- if it fails, the slot will eventually be freed by TTL, but there may be a short period of reduced capacity.


## The Advisory Endpoint

The `GET /v1/orders/{order_id}/advisory` endpoint provides customers with a non-binding estimate of when to leave for the restaurant. It reads the current window's usage and returns one of two recommendations:

### LEAVE_NOW

If available slots exist in the current window (current_reserved < max_concurrent), the advisory recommends leaving immediately:

```json
{
  "recommended_action": "LEAVE_NOW",
  "estimated_wait_seconds": 0,
  "suggested_leave_at": 1700000000,
  "available_slots": 3,
  "max_concurrent": 10,
  "is_estimate": true,
  "advisory_note": "Estimate only. Capacity is reserved only at arrival dispatch."
}
```

### WAIT

If the current window is full, the advisory recommends waiting until the next window:

```json
{
  "recommended_action": "WAIT",
  "estimated_wait_seconds": 180,
  "suggested_leave_at": 1700000300,
  "available_slots": 0,
  "max_concurrent": 10,
  "is_estimate": true,
  "advisory_note": "Estimate only. Capacity is reserved only at arrival dispatch."
}
```

### Why Advisory Only

The advisory endpoint explicitly does not reserve capacity. Every response includes `is_estimate: true` and a note that capacity is reserved only at dispatch time. This is critical for two reasons:

1. **No phantom reservations**: If the advisory reserved a slot, customers who check but never leave would consume capacity indefinitely.
2. **Accurate signal**: The advisory reflects the current state at query time. Between the query and the customer's actual arrival, other customers may arrive or cancel, changing the available capacity. Making promises based on stale data would be worse than providing honest estimates.


## max_concurrent_orders Configuration

Each restaurant has a `max_concurrent_orders` setting in its config record. The default is 10. This value can be adjusted through the restaurant config API by platform admins or the restaurant's own admin.

The capacity module reads this value at reservation time via `get_capacity_config()`, which falls back to defaults if the config table is unavailable:

- `max_concurrent_orders`: 10
- `capacity_window_seconds`: 300
- `dispatch_trigger_event`: 5_MIN_OUT

If `max_concurrent_orders` is set to zero or negative, the advisory endpoint permanently recommends WAIT, and no orders can be dispatched through the normal arrival flow. This effectively pauses the restaurant.


## WAITING_FOR_CAPACITY Status

When a customer arrives but no capacity slot is available, the order transitions to WAITING_FOR_CAPACITY rather than being rejected. This status:

1. Preserves the customer's place. The order remains active and valid.
2. Provides a `suggested_start_at` timestamp (the start of the next window) so the mobile app can show a countdown.
3. Allows automatic dispatch when the customer retries the vicinity signal after a slot frees up.

The WAITING status is distinct from PENDING because it conveys additional information: the customer has arrived but the restaurant is full. The mobile app can display a different UI for this state (e.g., "The restaurant is currently at capacity. Your order will be sent as soon as a slot opens.").

Orders in WAITING_FOR_CAPACITY are eligible for:
- **Re-dispatch**: When the customer sends another vicinity or arrival event, the system re-checks capacity and dispatches if a slot is now available.
- **Cancellation**: The customer can cancel while waiting.
- **Expiry**: If the order's `expires_at` passes while waiting, the expiry Lambda transitions it to EXPIRED.


## Force Fire as Override

The POS integration service provides a force-fire endpoint that bypasses the capacity system entirely. When a restaurant staff member force-fires an order, it transitions directly from PENDING or WAITING to SENT_TO_DESTINATION without checking or reserving capacity.

This override exists because real-world operations sometimes require manual intervention. A VIP customer, a phone order, or a situation where the GPS is not working are all cases where the restaurant needs to start preparing regardless of what the capacity system says. Force fire sets `receipt_mode: HARD` and `vicinity: True`, indicating that the restaurant has explicitly taken ownership of the order.

Force fire does not reserve a capacity slot, which means it can temporarily push the restaurant over its configured limit. This is intentional: the restaurant chose to accept the order, so the capacity system should not prevent it. However, the next regular arrival will see one fewer available slot because the force-fired order has not consumed a slot to release later. In practice, this self-corrects within one window as force-fired orders complete and regular capacity tracking resumes.
