# 07 - Capacity and Throughput

Version: 3.0
Last updated: 2026-02-21

## Capacity Model
Capacity is enforced per restaurant using fixed windows.

Config source (`RestaurantConfigTable`):
- `max_concurrent_orders` (default 10)
- `capacity_window_seconds` (default 300)

Window start calculation:
- `window_start = floor(now / window_seconds) * window_seconds`

## Reservation Primitive
On dispatch-eligible arrival event, orders service attempts an atomic counter increment in `CapacityTable`:
- key: (`restaurant_id`, `window_start`)
- condition: current count must be `< max_concurrent_orders`

Success:
- order can move to `SENT_TO_DESTINATION`

Failure:
- order remains/enters `WAITING_FOR_CAPACITY`
- `suggested_start_at` returned as next window boundary

## Release Behavior
Capacity slot release is attempted when:
- order is canceled
- order is completed via restaurant progression endpoint

## Advisory Endpoint
`GET /v1/orders/{order_id}/advisory` provides non-reserving guidance:
- `recommended_action`: `LEAVE_NOW` or `WAIT` (or follow-live status when already dispatched/closed)
- `estimated_wait_seconds`
- current/next window stats

## Throughput Tuning Guidance
- Lower `max_concurrent_orders` for overloaded kitchens.
- Increase `capacity_window_seconds` for smoother batching behavior.
- Monitor ratio of `WAITING_FOR_CAPACITY` to total dispatch attempts.
