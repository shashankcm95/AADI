# Restaurant Discovery Survey (Operational Intake)

Last updated: 2026-02-21

## Goal
Collect the minimum data needed to onboard and tune a restaurant for current Arrive behavior:
- catalog and menu quality
- capacity configuration
- POS connection readiness
- pickup/arrival workflow compatibility

## Section A: Basic Profile
1. Restaurant name
2. Address (street, city, state, zip)
3. Contact email
4. Cuisine
5. Price tier (1-4)
6. Operating hours/timezone

## Section B: Menu Readiness
1. Do you have CSV menu export with `Category,Name,Description,Price`?
2. Do menu items have stable IDs from POS?
3. Which items have long prep times?
4. Any items that should be hidden or unavailable by time of day?

## Section C: Capacity Inputs (Maps to current config)
1. `max_concurrent_orders` target for peak periods
2. `capacity_window_seconds` preference (300/600/900/1800)
3. Typical prep bottlenecks by hour/day
4. Policy for overload windows (wait messaging tolerance)

## Section D: Arrival Flow
1. How should staff react at `5_MIN_OUT`?
2. What action at `PARKING`?
3. What action at `AT_DOOR`?
4. Should `EXIT_VICINITY` auto-close when already fulfilling?

## Section E: POS Integration Readiness
1. POS provider (`square`, `toast`, `clover`, other)
2. Available webhook endpoint URL (HTTPS)
3. Secret management owner/process
4. Required permissions/scopes
5. Manual fallback if POS integration is unavailable

## Section F: Launch Risk Notes
1. Known constraints during rush hour
2. Staff training gaps
3. Escalation contacts
4. Acceptance criteria for go-live
