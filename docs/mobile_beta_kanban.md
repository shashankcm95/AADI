# Mobile Beta Readiness Board

Last updated: 2026-02-21

## Scope
`packages/mobile-ios` app readiness for controlled iOS beta.

## Completed
- Endpoints are split and configured by service (`restaurants`, `orders`, `users`) in `src/config.ts`.
- Arrival events are wired to backend `/v1/orders/{order_id}/vicinity` flow.
- Hybrid tracker now also sends raw location samples to `/v1/orders/{order_id}/location` for AWS Location ingestion.
- Customer app blocks admin/restaurant-admin users after login.
- Favorites, profile update, avatar upload, and cached order history are implemented.
- Capacity advisory endpoint is integrated in Order tracking screen.

## Active Risks
| Priority | Finding | Impact |
|---|---|---|
| Medium | AWS geofence cutover is disabled by default (shadow mode) | Auto-dispatch still depends on existing mobile/manual triggers until cutover is enabled |
| Medium | Mobile OS may suppress background location in edge conditions | Arrival automation can degrade; manual `"I'm Here"` remains required fallback |

## Current Gate Status
- Functional backend integration: pass (manual code-path verification)
- Python backend suites: pass
- Mobile lint/type/test in this local environment: partially blocked by file-read timeout issue in Node test runner context

## Recommended Next Gate
1. Validate AWS shadow telemetry against observed arrivals in device tests.
2. Define cutover SLOs (precision/recall, duplicate rates) and rollback toggles.
3. Execute device smoke test: login -> browse -> add to cart -> place order -> background approach -> dispatch.
