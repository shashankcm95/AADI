# Engineering Recovery Kanban

## Team
- SDE-Auth: Orders RBAC and ownership hardening
- SDE-Core: Payments/menu scope cleanup
- SDE-Test: Monorepo test reliability and fixture isolation
- SDE-Docs: Contract/status naming alignment
- SDE-Manager: Final quality gate

## Board
| Work Item | Owner | Status | Notes |
|---|---|---|---|
| Fail-closed auth in Orders Lambda | SDE-Auth | Done | Missing claims now return `401`; role checks stay `403` |
| Enforce role + ownership checks | SDE-Auth | Done | Customer vs restaurant/admin route separation maintained |
| Remove non-scope payment modes in POS create | SDE-Core | Done | Non-`PAY_AT_RESTAURANT` now rejected with `400` |
| Disable POS menu sync by default | SDE-Core | Done | Feature-gated via `POS_MENU_SYNC_ENABLED` |
| Remove dead/duplicate restaurants code | SDE-Core | Done | Duplicate Cognito pre-check removed; unreachable return removed |
| Align config/menu defaults | SDE-Core | Done | `active_menu_version=latest`; capacity defaults stored top-level |
| Stabilize root python test gate | SDE-Test | Done | Added isolated suite runner via `tests/test_python_suites.py` |
| Convert brittle unit script test | SDE-Test | Done | Replaced `exit(1)` script-style test with pytest fixture test |
| Update status naming in docs | SDE-Docs | Done | Replaced legacy `SENT_TO_RESTAURANT` terms |
| Manager gate | SDE-Manager | Done | Root `pytest -q` and per-suite tests passing |

## Manager Sign-off
- Date: 2026-02-15
- Gate checks:
  - `pytest -q services/orders/tests` ✅
  - `pytest -q services/pos-integration/tests` ✅
  - `pytest -q services/restaurants/tests` ✅
  - `pytest -q infrastructure/tests services/kitchen/tests tests/unit/test_admin_logic.py` ✅
  - `pytest -q` (root gate) ✅
