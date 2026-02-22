# Mock Usage Simulation (Reference Walkthrough)

Last updated: 2026-02-21
Status: Example scenario, not a protocol specification

## Scenario Summary
A customer places an order, approaches the restaurant, and the order transitions through backend states based on arrival events and capacity.

## Current-State Event/Status Mapping
- Customer places order -> `PENDING_NOT_SENT`
- Arrival events accepted by API:
  - `5_MIN_OUT`
  - `PARKING`
  - `AT_DOOR`
  - `EXIT_VICINITY`
- Capacity available on dispatch event -> `SENT_TO_DESTINATION`
- Capacity full -> `WAITING_FOR_CAPACITY`
- Restaurant/admin progression -> `IN_PROGRESS` -> `READY` -> `FULFILLING` -> `COMPLETED`

## Implementation Notes
- `EXIT_VICINITY` may auto-close fulfillment (`FULFILLING` -> `COMPLETED`) in orders engine.
- Arrival dispatch uses capacity reservation path for dispatch-eligible events.
- This simulation is useful for demos but not a replacement for API contracts.
