# Core Engine Contract

Version: 3.0
Last updated: 2026-02-21

## Purpose
Define the reusable decision contract for dispatching work only when eligibility and capacity conditions are satisfied.

## Generic Concepts
- Work item: unit of customer intent
- Destination/provider: entity with finite capacity
- Eligibility signal: customer-arrival or equivalent readiness input
- Capacity window: bounded counter bucket for dispatch safety

## Required Inputs
- current work-item state
- destination config (`window_seconds`, `max_units`)
- current time
- eligibility event/value

## Allowed Outcomes
1. Dispatch now
   - reserve capacity
   - transition to dispatched state
2. Wait
   - set waiting state and retry guidance
3. Reject/expire
   - if beyond expiry policy

## Invariants
- no overbooking within a capacity window
- monotonic state progression (no illegal backward transition)
- safe retries via conditional writes/idempotent contracts

## Arrive Mapping
- Work item -> order/session
- Destination -> restaurant
- Eligibility -> arrival events (`5_MIN_OUT`, `PARKING`, `AT_DOOR`)
- Dispatch state -> `SENT_TO_DESTINATION`
