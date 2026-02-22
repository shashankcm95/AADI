# Arrive User and Operator Manual

Last updated: 2026-02-21

## 1. Prerequisites
- Node.js 20+
- npm 9+
- Python 3.11+
- AWS SAM CLI (for backend template validation/deploy)

## 2. Install
From repo root:
```bash
npm ci
pip install -r infrastructure/requirements-dev.txt
pip install -r services/orders/requirements.txt
pip install -r services/restaurants/requirements.txt
```

## 3. Run Frontends Locally
From repo root:
```bash
npm run dev:customer
npm run dev:admin
npm run dev:ios
```

## 4. Backend Overview for Users
- Customer-facing APIs are consumed by customer web/mobile.
- Restaurant/admin operations use restaurants + orders routes.
- User profile APIs support profile edit + avatar upload URL.

## 5. Core User Flows
### Customer
1. Sign in.
2. Browse restaurants and menu.
3. Place order.
4. Send arrival updates (`5_MIN_OUT`, `PARKING`, `AT_DOOR`) or allow location-driven updates in mobile.
5. Track order status to completion.

### Restaurant Admin
1. Sign in to admin portal.
2. Select managed restaurant.
3. Maintain menu/config/images.
   - In Capacity settings, configure when pending orders should dispatch using `dispatch_trigger_event` (`5_MIN_OUT`, `PARKING`, `AT_DOOR`).
4. Monitor incoming orders.
5. Move orders through active lifecycle until completion.

## 6. Test Commands
```bash
pytest -q services/orders/tests
pytest -q services/restaurants/tests
pytest -q services/pos-integration/tests
pytest -q services/users/tests
pytest -q infrastructure/tests
pytest -q
npm run lint --workspace=packages/admin-portal
```

## 7. Troubleshooting
- `401/403` API errors: verify Cognito role claims (`custom:role`, `custom:restaurant_id`).
- Missing restaurant/menu data: verify service tables and active flags.
- Arrival updates not dispatching: verify capacity config and current window utilization.
- AWS geofence automation currently runs in shadow mode by default; if auto-dispatch is expected, verify `LOCATION_GEOFENCE_CUTOVER_ENABLED`.
- Avatar upload failure: verify users service bucket env and signed URL expiration window.

## 8. Current Known Issues
- POS service deployment requires manual stack path today.
- Mobile background delivery can still be constrained by iOS/Android power-management behavior; `"I'm Here"` remains fallback.
