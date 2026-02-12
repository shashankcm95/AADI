```markdown
# Agent Gamma: Fintech & Auto-Close Plan

## Objective
Implement the "Silent Exit". When the user drives away, the tab closes automatically.

## Logic Flow
1.  **Trigger**: `simulate_arrival_event` receives `EXIT_VICINITY`.
2.  **Engine**: `decide_arrival_update` handles `EXIT_VICINITY`.
    *   Condition: If `status` is `SERVING` or `COMPLETED`.
    *   Action: Set `payment_status` to `PAID` (Simulating capture).
    *   Action: Set `status` to `COMPLETED` (if not already).
3.  **Payment Adapter**: Ideally, we would call `capture_payment` here. For now, we update the model state to reflect the intent.

## Implementation Steps
### Backend (`services/orders/src`)
1.  **Update `models.py`**: Add `ARRIVAL_EXIT` constant.
2.  **Update `engine.py`**: Add `EXIT_VICINITY` handling to `decide_arrival_update`.
3.  **App Layer**: Ensure `simulate_arrival_event` passes this event through.

> **Note**: This document refers to a legacy version of the system. Ensure compatibility with the current architecture and update references as necessary.
```