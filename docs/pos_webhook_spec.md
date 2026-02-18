# AADI POS Outbound Push Specification

## Overview

This document defines the **outbound webhook payload** that AADI sends to
POS integrations (Square, Toast, Clover, etc.) when an order reaches the
`SENT_TO_DESTINATION` status — similar to how UberEats/DoorDash push orders
into restaurant POS systems.

> **Current state:** POS integration is undefined. This spec defines the
> outbound contract so that AADI can push new orders into any POS system
> that accepts a standard webhook, without requiring POS-specific adapters
> in the backend.

---

## Webhook Contract

### Endpoint

A restaurant configures a **POS Webhook URL** in their AADI restaurant
settings (stored in `RestaurantConfigTable` as `pos_webhook_url`).

When an order transitions to `SENT_TO_DESTINATION`, the orders service
calls:

```
POST {pos_webhook_url}
Content-Type: application/json
X-AADI-Signature: sha256={hmac_hex}
X-AADI-Event: order.sent
X-AADI-Delivery-Id: {uuid}
```

### Request Headers

| Header | Description |
|---|---|
| `Content-Type` | `application/json` |
| `X-AADI-Signature` | HMAC-SHA256 of the body using the restaurant's webhook secret |
| `X-AADI-Event` | Event type: `order.sent`, `order.updated`, `order.canceled` |
| `X-AADI-Delivery-Id` | Unique delivery ID for idempotency |

### Payload: `order.sent`

```json
{
  "event": "order.sent",
  "delivery_id": "del_abc123",
  "timestamp": "2026-02-17T21:30:00Z",
  "order": {
    "external_id": "ord_9f3a2bc4e1d0",
    "restaurant_id": "rest_xyz",
    "customer": {
      "name": "Jane D.",
      "phone_last_four": "4321"
    },
    "items": [
      {
        "pos_item_id": null,
        "name": "Margherita Pizza",
        "quantity": 2,
        "unit_price_cents": 1299,
        "modifiers": [],
        "notes": ""
      },
      {
        "pos_item_id": null,
        "name": "Caesar Salad",
        "quantity": 1,
        "unit_price_cents": 899,
        "modifiers": ["No croutons"],
        "notes": ""
      }
    ],
    "subtotal_cents": 3497,
    "arrive_fee_cents": 175,
    "total_cents": 3672,
    "payment_mode": "PAY_AT_RESTAURANT",
    "special_instructions": "",
    "estimated_arrival_minutes": null,
    "created_at": "2026-02-17T21:25:00Z"
  }
}
```

### Payload: `order.canceled`

```json
{
  "event": "order.canceled",
  "delivery_id": "del_def456",
  "timestamp": "2026-02-17T21:35:00Z",
  "order": {
    "external_id": "ord_9f3a2bc4e1d0",
    "restaurant_id": "rest_xyz",
    "reason": "customer_canceled"
  }
}
```

---

## Field Reference

| Field | Type | Description |
|---|---|---|
| `event` | string | One of: `order.sent`, `order.updated`, `order.canceled` |
| `delivery_id` | string | Unique per delivery attempt (for idempotency) |
| `timestamp` | ISO 8601 | When the event was generated |
| `order.external_id` | string | AADI order ID |
| `order.restaurant_id` | string | AADI restaurant ID |
| `order.items[].pos_item_id` | string\|null | Restaurant's POS item ID (null until menu mapping is configured) |
| `order.items[].name` | string | Human-readable item name |
| `order.items[].quantity` | int | Number ordered |
| `order.items[].unit_price_cents` | int | Price per unit in cents |
| `order.items[].modifiers` | string[] | Modifier names |
| `order.subtotal_cents` | int | Sum of all items |
| `order.arrive_fee_cents` | int | AADI platform fee |
| `order.total_cents` | int | subtotal + fee |
| `order.payment_mode` | string | Current: `PAY_AT_RESTAURANT` |

---

## Expected Response

| Status | Meaning |
|---|---|
| `200` or `201` | Order accepted — AADI marks delivery as successful |
| `409` | Duplicate — AADI marks delivery as already processed |
| `4xx` (other) | Rejected — AADI logs the rejection, does not retry |
| `5xx` | Temporary failure — AADI retries with exponential backoff (max 3 attempts) |
| Timeout (>10s) | Treated as 5xx — retry with backoff |

---

## Security

1. **HMAC Verification:** Each restaurant has a `pos_webhook_secret` stored in
   `RestaurantConfigTable`. The `X-AADI-Signature` header contains
   `sha256={HMAC-SHA256(body, secret)}`. POS receivers should verify this.

2. **HTTPS Only:** Webhook URLs must use `https://`.

3. **IP Allowlist (optional):** AADI Lambda functions run in the VPC. If
   the POS system supports IP allowlisting, the NAT Gateway EIPs can be
   provided.

---

## Implementation Phases

| Phase | Scope |
|---|---|
| **Phase 1 (this sprint)** | Define contract, add `pos_webhook_url` and `pos_webhook_secret` fields to restaurant config |
| **Phase 2** | Build webhook dispatcher Lambda triggered by DynamoDB Streams on Orders table |
| **Phase 3** | Add menu item ID mapping (link AADI items to POS catalog items) |
| **Phase 4** | Add adapter layer for Square/Toast/Clover-specific transformations |

---

## Restaurant Config Fields (Phase 1)

Add to `RestaurantConfigTable`:

```python
{
    "restaurant_id": "rest_xyz",
    # ... existing fields ...
    "pos_webhook_url": "https://api.squareup.com/v2/orders/webhook",   # POS endpoint
    "pos_webhook_secret": "whsec_...",                                  # HMAC secret
    "pos_provider": "square",                                           # square | toast | clover | custom
    "pos_enabled": false                                                # Feature flag
}
```
