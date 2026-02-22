# 08 - Error Handling, Retries, and Idempotency

Version: 3.0
Last updated: 2026-02-21

## Idempotency Controls
### Create order
- Supports `Idempotency-Key` when idempotency table is configured.
- First request stores `PROCESSING` lock; completion updates to `COMPLETED` with cached response body.

### Arrival/status paths
- Conditional status checks prevent invalid transitions.
- Repeated valid calls generally converge to the same state.

## Error Classes
- `400`: validation/body errors
- `401`: missing/invalid authentication
- `403`: role or ownership failure
- `404`: missing route/resource or ownership-obscured not-found
- `409`: invalid state/expired/order in-progress conflict
- `500`: unhandled execution failure

## Retry Behavior
- Safe retries are expected for read/list endpoints and idempotent updates.
- Capacity reservations are atomic and guarded by DynamoDB conditions.

## Current Known Gap
Under some concurrent update races, conditional write failures can bubble as generic errors if not mapped explicitly, resulting in `500` instead of a deterministic conflict response.
