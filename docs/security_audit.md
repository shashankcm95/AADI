# Security and Reliability Audit Snapshot

Last updated: 2026-02-26
Scope: `services/`, `packages/`, `infrastructure/`, CI/CD workflows

## Summary
The platform has strong baseline controls (Cognito auth on primary APIs, role checks, scoped table access). Several high-impact issues were fixed in code and now require deployment/verification in environment. Arrival reliability hardening is in progress with AWS Location shadow-mode ingestion and geofence event processing.

## Confirmed Strengths
- Cognito JWT authorizer is enabled by default for users/restaurants/orders service APIs.
- Orders and restaurants handlers enforce role/ownership checks.
- POS integration uses API-key auth and permission scoping (correct M2M pattern — no Cognito needed).
- Idempotency and conditional writes are used on critical order flows.
- TOCTOU capacity race condition fixed with `ConditionalCheckFailedException` handling and rollback.
- Structured JSON logging (`shared/logger.py`) replaces all `print()` and `traceback.print_exc()` calls.
- Unified `get_user_claims()` via shared Lambda Layer with consistent role fallback.
- Python test coverage: 280 tests across all services, running in isolated suite gate.

## Findings
| ID | Severity | Area | Finding | Recommendation | Status |
|---|---|---|---|---|---|
| A-01 | High | CORS/Auth | `Idempotency-Key` was missing from CORS allow headers while create-order depends on it | Keep header allowlists synced across Lambda + API Gateway | Fixed in code (pending deploy) |
| A-02 | High | Release Pipeline | CD invalidation referenced non-exported CloudFront output keys | Keep workflow/output contract tested in CI | Fixed in code + contract tests (pending deploy) |
| A-03 | High | Deployment Topology | POS service is not included in root infra stack | Add nested POS stack or document separate deployment as required | Fixed in code (optional via `DeployPosIntegration`) |
| A-04 | Medium | Data Wiring | POS template default table env names can drift from actual table names | Pass table names from stack outputs/parameters explicitly | Fixed |
| A-05 | Medium | Mobile Data Integrity | Mobile order-history timestamp conversion was incorrect for epoch seconds | Keep timestamp unit tests around render helpers | Fixed |
| A-06 | High | Geofencing Reliability | Mobile tracking depended on top-level `latitude`/`longitude` but restaurants data commonly stores `location.lat/lon` | Normalize coordinates in backend response and mobile client fallback | Fixed |
| A-07 | Medium | Arrival Triggering | AWS geofence integration is in shadow mode; authoritative cutover is not yet enabled | Validate shadow telemetry vs. mobile/manual triggers, then enable cutover with rollback plan | Control knobs fixed (`LocationGeofenceCutoverEnabled` + `LocationGeofenceForceShadow`), rollout pending |
| A-08 | Low | Test Isolation | Cross-service pytest runs can collide on generic module names (`app.py`) | Use isolated suite runs and service-bound imports in tests | Fixed |
| A-09 | Medium | Logging | Raw `print()` and `traceback.print_exc()` leaked unstructured data to CloudWatch | Replace with structured logger (`shared/logger.py`) | Fixed |
| A-10 | High | Race Condition | TOCTOU race in capacity reservation could double-book slots under load | Use DynamoDB conditional writes with rollback on `ConditionalCheckFailedException` | Fixed |
| A-11 | Medium | Code Duplication | CORS, auth, serialization duplicated across 3 services | Shared Lambda Layer (`services/shared/`) as single source of truth | Fixed |

## Current Residual Risk
- Background OS restrictions can still suppress mobile updates; fallback manual arrival trigger remains necessary.
- AWS geofence authoritative mode is still disabled by default until staging parity is validated.

## Priority Remediation Order
1. Deploy and verify A-01/A-02/A-03/A-04 changes in target environment
2. A-07 (enable AWS geofence cutover after validation)
3. Monitor background-delivery fallback usage and tune UX nudges around manual `"I'm Here"` fallback
