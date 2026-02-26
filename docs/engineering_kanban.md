# Engineering Status Board

Last updated: 2026-02-26

## Current Program Status
- Core backend services (`orders`, `restaurants`, `users`) are implemented and covered by 280 passing Python tests.
- Shared Lambda Layer (`services/shared/`) extracts CORS, auth, serialization, and logger — single source of truth.
- `pos-integration` is wire-ready in root infra behind `DeployPosIntegration` (default remains `false`).
- Frontend apps are active (`customer-web`, `admin-portal`, `mobile-ios`) and wired to deployed API endpoints.
- CloudWatch observability: metric filters, alarms, and dashboard provisioned.

## Verification Snapshot
- `pytest -q services/orders/tests`: 157 passed
- `pytest -q services/restaurants/tests`: 65 passed
- `pytest -q services/pos-integration/tests`: 36 passed
- `pytest -q services/users/tests`: 7 passed
- `pytest -q infrastructure/tests`: 14 passed
- `pytest tests/test_python_suites.py`: pass (isolated suite gate)
- `npm run lint --workspace=packages/admin-portal`: pass
- `npm test --workspace=packages/mobile-ios -- --watch=false`: pass
- `npx tsc --project packages/mobile-ios/tsconfig.ci.json --noEmit`: pass
- `npm run test --workspace=packages/customer-web -- --run`: pass (after pinning `react`/`react-dom` at `19.1.0` and adding `@testing-library/dom`)

## Open Engineering Findings
| Priority | Area | Finding | Status |
|---|---|---|---|
| High | Orders CORS | `Idempotency-Key` is used by create-order logic but not allowed in CORS headers/config. Browser clients cannot reliably send it cross-origin. | Fixed in code (pending deploy) |
| High | CD Pipeline | CloudFront invalidation steps reference output keys not exported by infra template (`CustomerWebDistributionId`, `AdminPortalDistributionId`). | Fixed in code + infra contract test (pending deploy) |
| High | POS Deployment | Main infrastructure stack does not include/deploy `services/pos-integration`. | Fixed in code (`DeployPosIntegration` toggle; defaults off) |
| Medium | POS Table Wiring | POS template uses generic table names (`${AWS::StackName}-orders`, `${AWS::StackName}-menus`) that do not match nested stack output names by default. | Fixed (explicit `OrdersTableName`/`MenusTableName` params) |
| High | Geofencing Reliability | Mobile geofencing can be skipped when restaurant coordinates are present only under `location.lat/lon`. | Fixed (backend + mobile fallback) |
| Medium | Dispatch Trigger Configurability | Restaurant admins need control over when pending orders move to incoming/dispatch. | Fixed (`dispatch_trigger_event` in config + admin portal) |
| Medium | AWS Geofence Cutover | Amazon Location tracker/geofence pipeline is implemented in shadow mode; AWS geofence events are not yet authoritative for state transitions. | Control plane fixed (`LocationGeofenceCutoverEnabled` + `LocationGeofenceForceShadow` rollback), rollout still pending |
| Medium | Background Signal Loss | Mobile OS background constraints can still suppress location delivery; manual `"I'm Here"` fallback is still required for worst-case continuity. | Open (platform constraint) |
| Low | Test Runner Isolation | Running orders + restaurants pytest files in one invocation can import the wrong `app` module due duplicate module names. | Fixed (restaurants tests bind conftest `app`; CI runs isolated suite gate) |

## Recently Completed (Sprints 2-4)
- Dead code cleanup: 7 unused imports removed across 5 files.
- `traceback.print_exc()` → structured logger (`req_log.error(exc_info=True)`).
- 62 inline response builders → `make_response()` across restaurants service.
- TOCTOU capacity race fix with `ConditionalCheckFailedException` handling.
- Shared Lambda Layer: extracted CORS, auth, serialization, logger (~330 lines deduplicated).
- Unified `get_user_claims()` across orders/restaurants/users.
- CloudWatch alarms, metrics, and dashboard provisioned.
- Users service added to suite gate.

## Next Execution Slice
1. Deploy updated infra stacks so shared layer, geofence controls, and POS wiring are live.
2. Run shadow-vs-authoritative parity checks for AWS geofence events in staging.
3. Enable cutover with `LocationGeofenceCutoverEnabled=true`; keep `LocationGeofenceForceShadow=true` ready as rollback switch.
4. Create SNS topic and attach to CloudWatch alarms for notification.
5. Decide when to enable `DeployPosIntegration=true` in production.
