# 09 - Operational Notes

Version: 3.0
Last updated: 2026-02-21

## Deployments
- Root infra stack: `infrastructure/template.yaml`
- Nested services deployed by root stack:
  - users
  - restaurants
  - orders

POS integration can be nested via infra parameter:
- `DeployPosIntegration=true` deploys `services/pos-integration/template.yaml`
- default remains `false` for staged rollout/testing

Amazon Location resources are now provisioned by root infra:
- Tracker (device positions)
- Geofence collection (restaurant geofences)
- Tracker consumer association (geofence evaluation)

## CI/CD Workflows
- `ci.yml`: backend tests + template validation + frontend lint/build
- `cd.yml`: backend deploy + frontend build/deploy/invalidation
- `mobile-eas.yml`: mobile validate + optional EAS build

## Health Endpoints
- Users: `GET /v1/users/health` (auth none)
- Restaurants: `GET /v1/restaurants/health` (currently still under default authorizer)

## Logging
- Orders service uses structured JSON logs via `services/orders/src/logger.py`.
- Geofence EventBridge consumer logs in `services/orders/src/geofence_events.py`.
- Other services primarily use print/logging defaults.

## Operational Risks to Watch
1. AWS geofence cutover is intentionally disabled by default (`LocationGeofenceCutoverEnabled=false`); rollback switch is `LocationGeofenceForceShadow`.
3. Mobile background signal delivery can still be constrained by OS power-management behavior.
4. POS stack can now be deployed from root infra, but should remain gated by rollout readiness (`DeployPosIntegration`).
