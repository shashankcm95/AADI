# 03 - Order Lifecycle

Version: 3.0
Last updated: 2026-02-21

## Canonical Statuses
- `PENDING_NOT_SENT`
- `WAITING_FOR_CAPACITY`
- `SENT_TO_DESTINATION`
- `IN_PROGRESS`
- `READY`
- `FULFILLING`
- `COMPLETED`
- `CANCELED`
- `EXPIRED`

## Arrival Events
Accepted customer arrival events:
- `5_MIN_OUT`
- `PARKING`
- `AT_DOOR`
- `EXIT_VICINITY`

Dispatch-eligible events: `5_MIN_OUT`, `PARKING`, `AT_DOOR`.
Restaurant config can raise the dispatch threshold with `dispatch_trigger_event`.
Example: if set to `PARKING`, `5_MIN_OUT` will update arrival metadata but not dispatch.

Current event sources:
- Mobile/manual client path -> `POST /v1/orders/{order_id}/vicinity` (authoritative)
- AWS Location EventBridge geofence ENTER path -> shadow mode unless cutover flag is enabled

## Transition Rules
### Customer-side dispatch transitions
- `PENDING_NOT_SENT` or `WAITING_FOR_CAPACITY` + dispatch-eligible event + capacity reserved
  -> `SENT_TO_DESTINATION`
- `PENDING_NOT_SENT` or `WAITING_FOR_CAPACITY` + dispatch-eligible event + no capacity
  -> `WAITING_FOR_CAPACITY`

### Restaurant-side progression transitions
- `SENT_TO_DESTINATION` -> `IN_PROGRESS`
- `IN_PROGRESS` -> `READY`
- `READY` -> `FULFILLING`
- `FULFILLING` -> `COMPLETED`

### Other transitions
- `PENDING_NOT_SENT` or `WAITING_FOR_CAPACITY` -> `CANCELED` (customer cancel endpoint)
- Any status checked after expiry may return conflict and update to `EXPIRED` path
- `EXIT_VICINITY` can auto-close `FULFILLING` orders to `COMPLETED`

## Receipt Modes
- On dispatch, order is stamped with soft receipt:
  - `receipt_mode = SOFT`
- Restaurant ack endpoint can upgrade to:
  - `receipt_mode = HARD`

## Invariants
- Dispatch requires capacity reservation in normal flow.
- Order cannot jump backward in restaurant progression chain.
- Cancel is blocked once order is sent/in-progress/closed.
