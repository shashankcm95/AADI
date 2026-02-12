```markdown
04 — API Reference

This document defines the public contract of the Arrive API (Version 2.1).

All endpoints are:

JSON over HTTPS

Deterministic

Backward-compatible within a major version

Base URL (example):

https://{api_id}.execute-api.{region}.amazonaws.com/v1

Authentication (v1)

None (prototype phase)

Restaurant/customer identity is inferred from request data

Auth will be layered later without breaking routes

Common Conventions
Headers
Content-Type: application/json

Timestamps

All timestamps are Unix epoch seconds (UTC)

ISO-8601 versions may be included for convenience

Error Format (Standard)
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation"
  }
}

POST /v1/orders

Create a new order.

Request Body
{
  "restaurant_id": "rst_001",
  "customer_name": "Shashank",
  "items": [
    {
      "id": "it_001",
      "qty": 1,
      "name": "Turkey Sandwich",
      "price_cents": 1099,
      "prep_units": 2
    }
  ]
}

Validation Rules

restaurant_id — required, string

items — required, non-empty list

qty, price_cents, prep_units default if omitted

Success Response — 201 Created
{
  "order_id": "ord_abc123",
  "status": "PENDING_NOT_SENT",
  "expires_at": 1768022354
}

Error Responses
Status	Code	Reason
400	VALIDATION	Missing or invalid fields
400	BAD_JSON	Malformed JSON
POST /v1/orders/{order_id}/vicinity

Signal whether the customer is physically near the restaurant.

This endpoint drives the state machine.

Request Body
{
  "vicinity": true
}

Behavior Summary
Current State	Capacity	Resulting State
PENDING_NOT_SENT	Available	SENT_TO_RESTAURANT
PENDING_NOT_SENT	Full	WAITING_FOR_CAPACITY
WAITING_FOR_CAPACITY	Available	SENT_TO_RESTAURANT
Any	Expired	EXPIRED
Success — Sent to Restaurant
{
  "order_id": "ord_abc123",
  "status": "SENT_TO_RESTAURANT",
  "vicinity": true
}

Success — Waiting for Capacity
{
  "order_id": "ord_abc123",
  "status": "WAITING_FOR_CAPACITY",
  "vicinity": true,
  "suggested_start_at": 1768018800,
  "suggested_start_at_iso": "2026-01-10T04:20:00+00:00",
  "retry_after_seconds": 503,
  "message": "Restaurant is at capacity. Start later to avoid waiting."
}

Error Responses
Status	Code	Reason
400	VALIDATION	vicinity not boolean
404	NOT_FOUND	Order does not exist
409	EXPIRED	Order expired
Idempotency Guarantees

Repeating the same vicinity call is safe

Capacity is never double-reserved

Final state always converges

GET /v1/restaurants/{restaurant_id}/orders

Fetch restaurant-facing order views.

Query Parameters
Name	Required	Description
status	yes	Order status to filter

Example:

/v1/restaurants/rst_001/orders?status=SENT_TO_RESTAURANT

Success Response — 200 OK
{
  "restaurant_id": "rst_001",
  "status": "SENT_TO_RESTAURANT",
  "orders": [
    {
      "order_id": "ord_abc123",
      "status": "SENT_TO_RESTAURANT",
      "created_at": 1768020554,
      "sent_at": 1768020602,
      "capacity_window_start": 1768020600,
      "customer_name": "Shashank",
      "items": [...],
      "prep_units_total": 3,
      "total_cents": 1298,
      "received_by_restaurant": true
    }
  ]
}

### POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack

Restaurant-side optional acknowledgement that an order was **received/seen**.

This endpoint is **optional**. By default, the system performs a "soft receipt" on dispatch
(`receipt_mode=SOFT`, `received_at=sent_at`). Calling this endpoint upgrades the receipt
to `HARD` and sets `received_at` to the time the restaurant acknowledged.

**Request Body**
```json
{
  "mode": "HARD"
}

200 OK (first time)

{
  "order_id": "ord_...",
  "receipt_mode": "HARD",
  "received_at": 1769747501
}


200 OK (idempotent repeat)

{
  "order_id": "ord_...",
  "receipt_mode": "HARD"
}


404 NOT_FOUND if order doesn't exist or restaurant mismatch

409 INVALID_STATE if order is not in SENT_TO_RESTAURANT

Sorting Rules

Sorted by sent_at

Fallback to created_at

Status Codes Summary
HTTP	Meaning
200	Successful read / transition
201	Resource created
400	Client error
404	Not found
409	State conflict (expired)
500	Unexpected server error
Design Guarantees

No endpoint causes silent side effects

No endpoint implicitly creates or deletes data

Every write is explicit and auditable

Next Document

Next we document Repository Structure & Code Ownership:

docs/05-repo-structure.md

Folder-by-folder explanation

Why each file exists

Where new logic should go

How to avoid a monolith
```