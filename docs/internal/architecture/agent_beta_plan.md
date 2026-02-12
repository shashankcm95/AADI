```markdown
# Agent Beta: Kitchen Conductor Plan

## Objective
Transform the Admin Portal from a passive "Order List" to an active "Kitchen Operating System".

## Data Model Changes
### 1. KDS Lanes
Instead of just `status`, the KDS needs to group orders by "Lane".
*   **Prep Lane**: `ARRIVAL_5_MIN` or `PENDING` (if auto-fire).
*   **Cook Lane**: `ARRIVAL_PARKING` or `IN_PROGRESS`.
*   **Plate Lane**: `ARRIVAL_DOOR` or `READY`.

### 2. The "Heartbeat" (Pacing)
We need a way to measure kitchen stress.
*   New entity: `KitchenState` (per restaurant).
*   Fields: `active_tickets`, `avg_ticket_time`, `stress_level` (LOW, MED, HIGH).

## Implementation Steps
### Backend (`services/orders`)
1.  **Update `list_restaurant_orders`**: Add `group_by=lanes` parameter to pre-sort orders into lanes for the frontend.
2.  **New Endpoint `GET /v1/restaurants/{id}/heartbeat`**: Returns the calculated stress level based on active capacity.
3.  **Pacing Logic**: If `stress_level == HIGH`, `decide_vicinity_update` should add a "Throttle" delay (e.g. `suggested_start_at += 10 mins`).

## Frontend (`admin-portal`)
1.  **New View**: `KanbanBoard`.
2.  **Sound Engine**: Play "Ding" on new order in Prep Lane.

> **Note:** This document describes a legacy version of the system. Please refer to the current implementation files in the `services/orders` and `admin-portal` directories for the latest updates.
```