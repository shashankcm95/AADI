```markdown
10.1 Order Acknowledgement by Restaurant
Problem

Currently:

Order is considered SENT_TO_RESTAURANT once capacity is reserved

Options

Soft Ack (Recommended)

Restaurant UI auto-receives

System assumes acceptance

Hard Ack

Restaurant explicitly taps “Accept”

More accurate, higher operational cost

Recommendation

Start with soft-ack + SLA monitoring
Add hard-ack only for high-volume restaurants

10.2 Background Scheduler

Introduce a worker that:

Promotes WAITING_FOR_CAPACITY → SENT_TO_RESTAURANT

Releases expired capacity

Cleans stale orders

Implementation Options

AWS Lambda with EventBridge scheduling

Step Functions

SQS delayed queues

10.3 Capacity Model Enhancements

Future improvements:

Rolling windows instead of fixed buckets

Prep unit decay over time

Priority orders

Per-item prep weighting

10.4 Payment & No-Show Handling

Potential additions:

Payment authorization on SENT

Capture on RECEIVED

Cancellation penalties

No-show tracking per customer

10.5 Restaurant Experience

Tablet UI

Order acknowledgment

Prep timers

Load indicators (“5 orders ahead of you”)

10.6 Customer Experience

ETA confidence bands

Push notifications

Retry hints

“Leave now / Wait X minutes” guidance

10.7 Platform Hardening

Authentication (Cognito)

Rate limiting

Structured metrics (CloudWatch EMF)

Dead-letter queues

Canary deployments

10.8 Data & Analytics

Prep unit utilization

Wait time distributions

Restaurant performance

Capacity tuning recommendations

10.9 Monorepo / Service Split

Future paths:

Split Orders vs Capacity

Shared infra package

Event-driven architecture

10.10 What Will Not Be Added (By Design)

Real-time kitchen scheduling

Full POS replacement

Complex forecasting in v1

**Version:** 2.1
**Date:** 2026-02-12
```