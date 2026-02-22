# 10 - Future Considerations

Version: 3.0
Last updated: 2026-02-21

## Near-Term
1. Integrate POS service into root infrastructure deployment path.
2. Validate AWS geofence shadow metrics and define cutover/rollback thresholds.
3. Enable AWS geofence cutover toggle after field validation.
4. Add stronger frontend CI reliability checks for mobile/customer-web test runners.

## Mid-Term
1. Add richer observability and metrics dashboards (dispatch rate, capacity pressure, wait-time distributions).
2. Improve race handling for conditional update conflicts with explicit error mapping.
3. Add stronger transactional semantics around capacity + order update coherence.
4. Add restaurant single-item read endpoint to avoid list-filter client workaround.

## Longer-Term
1. Optional real-time push channel for restaurant operations.
2. Google and additional identity providers in Cognito flow.
3. More adaptive capacity tuning (time-of-day curves, menu-weighted costs).
4. POS onboarding automation and key lifecycle management tooling.
