```markdown
09 – Operational Notes

This document covers runtime behavior, observability, operational safety, and debugging for the current backend architecture.

**Version:** 2.1
**Date:** 2026-02-12

9.1 Deployment Model

Runtime: AWS Lambda (Python 3.11)

IaC: AWS SAM (template.yaml)

Environment: arrive-dev (single environment so far)

Deploy Command:

```bash
sam build
sam deploy
```

⚠️ Note: `sam build --clean` is not supported. To force a clean build, remove `.aws-sam/` manually.

## Smoke test (local)

With `sam local start-api` running:

```bash
cd services/orders
./scripts/smoke_local.sh
```

9.2 DynamoDB Tables & Responsibilities

Orders Table

Purpose

Source of truth for order lifecycle

Key Fields

- order_id (PK)
- restaurant_id
- status
- created_at
- sent_at
- expires_at
- prep_units_total
- vicinity

Indexes

- GSI_RestaurantStatus (restaurant_id + status)

Used by restaurant-facing order lists

RestaurantConfig Table

Purpose

Per-restaurant operational configuration

Key Fields

- restaurant_id (PK)
- capacity_window_seconds (default: 600)
- max_prep_units_per_window (default: 20)

Changes here take effect immediately for new vicinity checks.

Capacity Table

Purpose

Enforces prep capacity per restaurant per time window

Key Fields

- restaurant_id (PK)
- window_start (SK)
- used_units
- ttl

Notes

- Capacity is reserved optimistically
- TTL cleanup is best-effort via DynamoDB TTL
- Window granularity is fixed by capacity_window_seconds

9.3 Capacity Reservation Semantics (Important)

Capacity reservation is:

✅ Atomic per window

❌ Not transactional across multiple windows

❌ Not released on order expiry (yet)

What this means

- Capacity may be over-reserved temporarily
- System favors restaurant protection over customer immediacy
- This is acceptable for v0 / prototype

9.4 Order Lifecycle Guarantees

Guaranteed

- An order is only marked SENT_TO_RESTAURANT if:
  - Customer is in vicinity
  - Capacity reservation succeeds
- Orders past expires_at are rejected

Best-Effort

- TTL cleanup
- Capacity release
- Ordering between multiple concurrent orders
- Idempotency for repeated vicinity calls

9.5 Observability & Debugging

CloudWatch Logs

Each Lambda invocation logs:

- Request lifecycle
- Capacity reservation failures
- Syntax/runtime errors

Primary log group

`/aws/lambda/arrive-dev-OrdersFunction-*`

Tail logs

```bash
aws logs tail "/aws/lambda/arrive-dev-OrdersFunction-*" --since 10m --follow
```

Common Errors & Meaning

| Error                  | Meaning                  | Action                  |
|------------------------|--------------------------|-------------------------|
| Internal Server Error  | Lambda exception         | Check CloudWatch logs   |
| WAITING_FOR_CAPACITY   | Capacity exhausted       | Client should retry later |
| NOT_FOUND              | Bad order_id             | Client bug              |
| EXPIRED                | Order too old            | Client must recreate    |

9.6 Safe Operational Practices

- Never manually edit Capacity table (except during debugging)
- Prefer changing max_prep_units_per_window instead
- Avoid backdating timestamps
- Do not rely on TTL for correctness

9.7 Known Limitations (Explicit)

- No idempotency keys
- No payment integration
- No auth / identity
- No background workers
- No reconciliation jobs
- No metrics beyond logs

These are intentional and documented.
```