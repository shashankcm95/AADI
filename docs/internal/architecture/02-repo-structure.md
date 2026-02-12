```markdown
02 — Repository Structure

**Version:** 2.1
**Date:** 2026-02-12

Top-Level Layout

```
.
├── verify_integration.py
├── turbo.json
├── amplify.yml
├── package-lock.json
├── package.json
├── .eslintrc.json
├── tools/
│   ├── sde-team/
│   │   ├── agents.py
│   │   ├── utils.py
│   │   └── main.py
│   └── mock-server/
│       ├── index.js
│       └── data/
│           └── seed_restaurants.json
├── .turbo/
├── packages/
│   ├── customer-web/
│   │   ├── vite.config.js
│   │   ├── package.json
│   │   └── src/
│   ├── mobile-ios/
│   │   ├── app.json
│   │   ├── package.json
│   │   └── src/
│   └── admin-portal/
│       ├── vite.config.js
│       ├── package.json
│       └── src/
├── .github/
│   └── workflows/
├── infrastructure/
│   ├── template.yaml
│   ├── tests/
│   └── scripts/
├── .aws-sam/
├── services/
│   ├── restaurants/
│   │   ├── template.yaml
│   │   └── src/
│   ├── pos-integration/
│   │   ├── template.yaml
│   │   └── src/
│   ├── orders/
│   │   ├── template.yaml
│   │   └── src/
│   └── kitchen/
│       ├── template.yaml
│       └── src/
```

This structure is intentional and optimized for:

- AWS SAM deployment
- Clear service boundaries
- Minimal coupling between domains

**Infrastructure + Runtime Code**

This directory contains everything that is deployed.

**template.yaml**

Role:
- AWS SAM template defining:
  - Lambda functions
  - API Gateway routes
  - DynamoDB tables
  - IAM permissions
  - Environment variables

Why this matters:
- It is the single source of truth for infrastructure
- No hidden resources exist outside this file
- Changes here should be treated as system-level changes

**src/ — Lambda Source Code**

Each domain gets its own folder.

This prevents:
- God Lambdas
- Circular dependencies
- Accidental cross-domain coupling

**services/orders/src/app.py**

Domain: Entry Point & Routing

Responsibilities:
- Authenticates requests
- Routes to `handlers/` modules (`customer.py`, `restaurant.py`)
- Standardizes error responses

**services/orders/src/handlers/**

Domain: Business Logic

Responsibilities:
- `customer.py`: Order creation, vicinity updates
- `restaurant.py`: Order listing, acknowledgments


**infrastructure/src/app.py**

Domain: Operational health

Responsibilities:
- Lightweight health checks
- Deployment verification
- Monitoring hooks

Why it exists separately:
- Avoids coupling system health to business logic
- Keeps uptime checks cheap and reliable

**scripts/seed/ — Non-Production Utilities**

Purpose:
- Manual development seeding
- Testing workflows
- Local or sandbox environments only

Important rules:
- These files are not runtime dependencies
- They must not be referenced by Lambda code
- JSON seed data should be gitignored if it becomes environment-specific

**.github/workflows/ — CI/CD Pipelines**

This folder contains configuration for continuous integration and deployment workflows.

**How to Add New Features Safely**

When extending the system:

**New Domain?**

Create:
- `services/<domain>/src/app.py`

Add:
- A new Lambda
- Explicit routes
- Clear ownership

**New Behavior in Orders?**

Extend `orders/src/app.py`
- Update documentation first
- Add state transitions explicitly

**New Infrastructure?**

Update `template.yaml`
- Treat as a breaking-change surface
- Document assumptions immediately

**Why This Structure Scales**

- Domains are isolated
- Deployment remains predictable
- Debugging is localized
- Documentation mirrors reality

This repo will stay understandable even as the system grows.

**Next Document**

Next we’ll define the Order State Machine formally:

`docs/03-order-lifecycle.md`

- States
- Transitions
- Guards
- Failure cases
- Invariants
```