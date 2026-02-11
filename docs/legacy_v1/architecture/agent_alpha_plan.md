# Agent Alpha: Geospatial Engine Plan

## Objective
Implement "Progressive Arrival" logic. The system must track the customer through distinct stages to orchestrate the kitchen perfectly.

## Data Model Changes
### 1. New Statuses (Micro-States)
Currently, we store `vicinity: bool`. We need richer state.
Instead of changing `Order.status` (which tracks the Kitchen workflow), we will add `Order.arrival_status`.

*   `ARRIVAL_UNKNOWN` (Default)
*   `ARRIVAL_5_MIN` (Trigger: "Fire the Patty")
*   `ARRIVAL_PARKING` (Trigger: "Toast Bun")
*   `ARRIVAL_DOOR` (Trigger: "Plate")

### 2. Interfaces (`src_orders/core/geo.py`)
*   `GeoPort`: Interface to calculate ETA / Distance.

### 3. Engine Logic (`decide_arrival_update`)
*   New decision function in `engine.py`.
*   Input: `current_order`, `event_type` (e.g., `GEO_ENTER_5_MIN`).
*   Output: `UpdatePlan` that sets `arrival_status` and potentially auto-advances `Order.status` (e.g., WAITING -> SENT).

## Implementation Steps
1.  Define `ArrivalStatus` constants in `models.py`.
2.  Update `Order` model to include `arrival_status`.
3.  Create `decide_arrival_update` in `engine.py`.
4.  Expose `POST /v1/orders/{id}/simulate_arrival` to allow detailed demo control.
