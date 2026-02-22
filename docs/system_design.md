# Arrive Platform System Design (Current)

Version: 3.0
Last updated: 2026-02-21

## 1. System Purpose
Arrive is a capacity-aware order orchestration platform. It delays dispatch to restaurant operations until customer arrival intent and capacity checks align.

## 2. Deployed Core Services
- `users` service: customer profile and avatar workflows
- `restaurants` service: restaurant catalog, menu, capacity/POS config, favorites, media upload URL generation
- `orders` service: order lifecycle, capacity gating, advisory, cancellation, restaurant-side progression

Note: `pos-integration` is now wired in root infra behind `DeployPosIntegration` (default `false` for staged rollout).

## 3. High-Level Request Flow
1. Customer authenticates via Cognito.
2. Customer app reads restaurants/menu and creates order.
3. Order starts `PENDING_NOT_SENT`.
4. Arrival events come from:
   - mobile background geofencing (`expo-location` + task manager), or
   - AWS Location geofence ENTER events (shadow mode in current code), or
   - manual client action (`I'm Here`) fallback.
5. Dispatch-eligible event (`5_MIN_OUT`, `PARKING`, `AT_DOOR`) triggers capacity reservation attempt.
   - Trigger threshold is restaurant-configurable via `dispatch_trigger_event` in restaurant config.
6. Success -> `SENT_TO_DESTINATION`; full -> `WAITING_FOR_CAPACITY`.
7. Restaurant/admin progresses order: `IN_PROGRESS` -> `READY` -> `FULFILLING` -> `COMPLETED`.

## 4. Data Stores
- Orders service:
  - `OrdersTable`
  - `CapacityTable`
  - `IdempotencyTable`
  - `GeofenceEventsTable` (dedupe for EventBridge geofence events)
- Restaurants service:
  - `RestaurantsTable`
  - `MenusTable`
  - `RestaurantConfigTable`
  - `FavoritesTable`
- Users service:
  - `UsersTable`
- Optional POS service:
  - `PosApiKeysTable`
  - `PosWebhookLogsTable`

## 5. Auth and Authorization
- Users/restaurants/orders APIs: Cognito JWT authorizer.
- POS APIs: `X-POS-API-Key` with permission checks.
- Orders role model:
  - customer routes: customer-only
  - restaurant routes: admin/restaurant_admin with ownership checks for restaurant_admin.

## 6. Frontend Surfaces
- `packages/customer-web`: customer ordering web app
- `packages/admin-portal`: restaurant admin operations and kanban view
- `packages/mobile-ios`: React Native iOS customer app with arrival tracking

## 7. Known Gaps
- Google OAuth parameters exist in infra but Google IdP provisioning is not yet implemented.
- AWS geofence path is shadow mode by default (`LocationGeofenceCutoverEnabled=false`), with rollback switch available (`LocationGeofenceForceShadow=true`).
- POS stack remains operator-toggled (`DeployPosIntegration=false` by default) until rollout validation completes.

## 8. Operational State
- Backend Python suites are passing.
- Core flow is stable for create/list/update lifecycle.
- Open bugs and risks are tracked in `docs/engineering_kanban.md` and `docs/security_audit.md`.
