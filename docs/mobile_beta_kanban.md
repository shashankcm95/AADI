# Mobile Beta Launch Kanban

## Team
- SDE-Config: endpoint and auth configuration alignment
- SDE-App: customer flow hardening and mock removal
- SDE-Security: iOS transport/privacy settings hardening
- SDE-QA: integration validation and release checklist
- SDE-Manager: final gate and beta launch recommendation

## Board
| Work Item | Owner | Status | Notes |
|---|---|---|---|
| Align mobile endpoints with deployed customer-web APIs | SDE-Config | Done | Added `src/aws-exports.ts` and `src/config.ts` with restaurants/orders URLs |
| Split mobile API client by service gateway | SDE-Config | Done | `restaurants/*` routes now use Restaurants API; `orders/*` routes use Orders API |
| Remove demo-only service path from app flow | SDE-App | Done | Removed `DepartureScreen` (mock recommendation flow) from navigation and codebase |
| Remove hardcoded demo credentials from login UI | SDE-App | Done | Deleted test credential block from `LoginScreen` |
| Enforce customer-only role access in customer app | SDE-App | Done | Block `admin` and `restaurant_admin` identities after sign-in |
| Remove fake restaurant coordinate fallbacks | SDE-App | Done | Replaced Austin fallback with real restaurant coordinates only |
| Convert arrival controls from simulation framing to real API actions | SDE-App | Done | Arrival actions now call live `/v1/orders/{order_id}/vicinity` endpoint |
| Fix status mismatch (`CANCELLED` -> `CANCELED`) | SDE-App | Done | Terminal-state handling now matches backend status enum |
| Enforce strict background permission return | SDE-Security | Done | `requestPermissions()` now returns true only when background permission is granted |
| Remove permissive ATS setting for iOS | SDE-Security | Done | Removed `NSAllowsArbitraryLoads`; retained local networking flag |
| Declare background location mode in app config | SDE-Security | Done | Added `UIBackgroundModes: ["location","fetch"]` in Expo/iOS config |
| Manager gate checks | SDE-Manager | Done | See validation log below |

## Validation Log (Manager Gate)
- `python` endpoint parity check against web config: PASS
  - Restaurants URL parity: `True`
  - Orders URL parity: `True`
- Static contract inspection (`rg`) for mobile service URLs: PASS
  - Restaurants calls use `RESTAURANTS_API_BASE_URL`
  - Orders calls use `ORDERS_API_BASE_URL`
- `npm test -- --watch=false` in `packages/mobile-ios`: BLOCKED
  - Reason: `jest: command not found` (workspace dependencies not installed)
- `npx tsc --noEmit` in `packages/mobile-ios`: BLOCKED
  - Reason: offline registry resolution failure (`ENOTFOUND registry.npmjs.org`)

## Manager Review
- Date: 2026-02-15
- Decision: **Conditionally approved for beta dry-run in controlled TestFlight**, pending dependency install and full JS test/type gate in CI or a network-enabled environment.
- Must-pass before broader beta invite:
  1. Run `npm ci` at repo root (or workspace install for `mobile-ios`)
  2. Run `npm test --workspace=packages/mobile-ios -- --watch=false`
  3. Run `npx tsc --noEmit` in `packages/mobile-ios`
  4. Smoke-test on physical iOS device: login, restaurants list, menu load, place order, status refresh, arrival event update
