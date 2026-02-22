# 02 - Repository Structure

Version: 3.0
Last updated: 2026-02-21

## Top-Level Layout
```text
packages/
  customer-web/
  admin-portal/
  mobile-ios/

services/
  users/
  restaurants/
  orders/
  pos-integration/

infrastructure/
  template.yaml
  src/
  scripts/

docs/
  (product, operations, architecture docs)
```

## Ownership by Domain
- `services/orders`: lifecycle engine, dispatch gating, restaurant progression
- `services/restaurants`: restaurant CRUD, menu, config, favorites, image upload URLs
- `services/users`: profile and avatar endpoints
- `services/pos-integration`: API-key POS adapter and webhook ingress
- `packages/*`: user/admin/mobile clients

## Important Clarifications
- There is no active `services/kitchen` folder in current codebase.
- POS service exists but is not wired as a nested app in root `infrastructure/template.yaml`.
- Documentation under `docs/internal/architecture` is authoritative over older narrative docs.
