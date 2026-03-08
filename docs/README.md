# Arrive Platform Documentation

Welcome to the Arrive documentation. This is the single source of truth for understanding, building, deploying, and operating the Arrive platform.

## What Is Arrive?

Arrive is a dine-in restaurant ordering platform that enables customers to order directly from their table using a web or mobile app. The platform uses real-time location tracking to confirm the customer is at the restaurant and coordinates kitchen capacity so food is prepared fresh and served to the table.

The platform consists of four backend services (Orders, Restaurants, Users, POS Integration), two web frontends (Customer Web, Admin Portal), and a React Native iOS mobile app, all deployed on AWS using SAM/CloudFormation.

## Documentation Map

### [Product](./product/)
*For investors, business stakeholders, and anyone evaluating the platform.*

| Document | Description |
|----------|-------------|
| [Platform Overview](./product/platform-overview.md) | What Arrive is, how it works, the three-sided coordination model, and technical maturity |
| [Roadmap](./product/roadmap.md) | What's built today, what's coming next, and longer-term vision |

### [Guides](./guides/)
*For restaurant partners and end users.*

| Document | Description |
|----------|-------------|
| [Customer Guide](./guides/customer-guide.md) | How customers browse, order from their table, and track their dine-in order |
| [Restaurant Onboarding](./guides/restaurant-onboarding.md) | What restaurant partners need to know to get started on Arrive |
| [Admin Portal Guide](./guides/admin-portal-guide.md) | Day-to-day restaurant management — menus, orders, capacity, POS settings |

### [Developer](./developer/)
*For engineers contributing to the codebase.*

| Document | Description |
|----------|-------------|
| [Getting Started](./developer/getting-started.md) | Clone, install, run, and test in under 10 minutes |
| [Architecture](./developer/architecture.md) | System design, service boundaries, data flow, and key design decisions |
| [API Reference](./developer/api-reference.md) | Every endpoint across all four services — methods, paths, auth, payloads, errors |
| [Order Lifecycle](./developer/order-lifecycle.md) | The state machine at the heart of Arrive — statuses, transitions, dispatch logic, capacity |
| [Data Model](./developer/data-model.md) | DynamoDB tables, schemas, GSIs, and access patterns |
| [Auth and Access Control](./developer/auth-and-access-control.md) | Cognito JWT, POS API keys, role-based access, and how claims flow through the system |
| [Testing](./developer/testing.md) | 467 tests across 4 services — how to run them, how to write them, mocking patterns |
| **Service Deep Dives** | |
| [Orders Service](./developer/services/orders.md) | The dispatch engine, location bridge, capacity management, and order handlers |
| [Restaurants Service](./developer/services/restaurants.md) | Menu management, restaurant config, image uploads, geofencing |
| [Users Service](./developer/services/users.md) | User profiles, avatar uploads, Cognito post-confirmation |
| [POS Integration](./developer/services/pos-integration.md) | API key authentication, webhook processing, menu sync, order mapping |
| [Shared Layer](./developer/services/shared-layer.md) | The Lambda Layer powering CORS, auth, logging, and serialization across all services |

### [Operations](./operations/)
*For anyone deploying, monitoring, or maintaining the platform.*

| Document | Description |
|----------|-------------|
| [Deployment](./operations/deployment.md) | SAM deployment, CloudFormation parameters, environment setup |
| [CI/CD](./operations/ci-cd.md) | GitHub Actions workflows — what each check does and how to fix failures |
| [Infrastructure](./operations/infrastructure.md) | CloudFormation resources, nested stacks, networking, and storage |
| [Monitoring and Logging](./operations/monitoring-and-logging.md) | Structured logging with structlog, CloudWatch integration, operational visibility |
| [Security](./operations/security.md) | Security model, hardening measures, audit findings, and residual risks |
| [Troubleshooting](./operations/troubleshooting.md) | Common issues, diagnostic steps, rollback procedures |

### [Reference](./reference/)
*Appendices and lookup material.*

| Document | Description |
|----------|-------------|
| [POS Webhook Specification](./reference/pos-webhook-spec.md) | Webhook contract for POS system integration |
| [Capacity Model](./reference/capacity-model.md) | Throughput design, time-window mechanics, reservation logic |
| [Glossary](./reference/glossary.md) | Terms, statuses, abbreviations, and domain concepts |

## Quick Links

- **I want to run the project locally** → [Getting Started](./developer/getting-started.md)
- **I want to understand how orders work** → [Order Lifecycle](./developer/order-lifecycle.md)
- **I want to deploy to AWS** → [Deployment](./operations/deployment.md)
- **I want to add a new API endpoint** → [Architecture](./developer/architecture.md) then the relevant [Service Deep Dive](./developer/services/)
- **I want to understand the business** → [Platform Overview](./product/platform-overview.md)
- **I'm a restaurant partner** → [Restaurant Onboarding](./guides/restaurant-onboarding.md)
- **Tests are failing** → [Testing](./developer/testing.md) or [Troubleshooting](./operations/troubleshooting.md)
