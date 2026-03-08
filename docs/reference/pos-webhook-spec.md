# POS Webhook Specification

This document defines the contract for POS systems delivering webhook events to the Arrive platform. The webhook endpoint accepts order lifecycle events and processes them idempotently.


## Endpoint

```
POST /v1/pos/webhook
```


## Authentication

Every request must include the `X-POS-API-Key` header containing the raw API key assigned to the POS integration. The platform hashes this key with SHA-256 and looks up the hash in the key store. Keys that are expired (past their TTL) or not found are rejected.

The API key must have the `orders:write` permission. This is required because webhook events can trigger order creation and status changes, both of which are write operations.

```
X-POS-API-Key: pos_live_abc123def456...
```

Requests without a valid API key receive a 401 response:

```json
{
  "error": "Unauthorized",
  "message": "Missing or invalid X-POS-API-Key header"
}
```

Requests with a valid key that lacks `orders:write` permission receive a 403 response:

```json
{
  "error": "Forbidden",
  "message": "API key does not have required permission: orders:write"
}
```


## Request Format

The request body must be a JSON object with the following fields:

| Field         | Type   | Required | Description                                                  |
|--------------|--------|----------|--------------------------------------------------------------|
| `webhook_id` | string | Yes      | Unique identifier for this event. Used for idempotency.       |
| `event_type` | string | Yes      | The type of event. See Supported Event Types below.           |
| `data`       | object | Yes      | Event-specific payload. Structure depends on event_type.      |

The `webhook_id` field can also be provided as `event_id`. If neither is present, the platform generates an ID and logs a warning. POS systems should always provide their own ID to ensure deduplication works correctly across retries.


## Supported Event Types

### order.created

Fired when a new order is placed in the POS. Also accepted as `order.placed`.

The `data` object should contain the order details in the POS system's native format. The platform uses the API key's `pos_system` field to determine which format mapper to apply.

**Generic format example:**

```json
{
  "webhook_id": "evt_20240301_001",
  "event_type": "order.created",
  "data": {
    "items": [
      {
        "id": "item-001",
        "name": "Margherita Pizza",
        "qty": 2,
        "price_cents": 1299,
        "work_units": 3
      },
      {
        "id": "item-002",
        "name": "Caesar Salad",
        "qty": 1,
        "price_cents": 899,
        "work_units": 1
      }
    ],
    "customer_name": "Jane Smith",
    "pos_order_ref": "POS-12345"
  }
}
```

**Toast format example:**

```json
{
  "webhook_id": "toast_evt_abc123",
  "event_type": "order.created",
  "data": {
    "guid": "toast-order-guid-001",
    "checks": [
      {
        "selections": [
          {
            "guid": "sel-001",
            "displayName": "Margherita Pizza",
            "quantity": 2,
            "price": 12.99,
            "prepTimeMinutes": 3
          }
        ]
      }
    ],
    "customer": {
      "firstName": "Jane"
    }
  }
}
```

**Square format example:**

```json
{
  "webhook_id": "sq_evt_xyz789",
  "event_type": "order.created",
  "data": {
    "id": "sq-order-id-001",
    "line_items": [
      {
        "catalog_object_id": "cat-001",
        "name": "Margherita Pizza",
        "quantity": "2",
        "base_price_money": {
          "amount": 1299
        }
      }
    ],
    "customer_name": "Jane Smith"
  }
}
```

The `restaurant_id` in the order data is always overridden by the restaurant bound to the API key. This prevents a POS system from creating orders for a different restaurant.

**Success response** (201):

```json
{
  "arrive_order_id": "ord_pos_abc123def456",
  "pos_order_ref": "POS-12345",
  "status": "PENDING_NOT_SENT",
  "arrive_fee_cents": 50
}
```


### order_status.changed

Fired when an order's status changes in the POS. Also accepted as `order.updated`.

The `data` object must contain `order_id` (the Arrive order ID) and `status` (the new status).

**Request example:**

```json
{
  "webhook_id": "evt_20240301_002",
  "event_type": "order_status.changed",
  "data": {
    "order_id": "ord_pos_abc123def456",
    "status": "PREPARING"
  }
}
```

**Valid POS status values and their Arrive mappings:**

| POS Status  | Arrive Status          |
|------------|------------------------|
| PREPARING  | IN_PROGRESS            |
| READY      | READY                  |
| PICKED_UP  | FULFILLING             |
| COMPLETED  | COMPLETED              |

Arrive-native status values (IN_PROGRESS, READY, FULFILLING, COMPLETED) are also accepted.

**Success response** (200):

```json
{
  "order_id": "ord_pos_abc123def456",
  "status": "IN_PROGRESS"
}
```


## Idempotency Behavior

The webhook endpoint is idempotent. Each `webhook_id` is recorded in the POS webhook logs table with a 7-day TTL. If the same `webhook_id` is received again within 7 days, the endpoint returns 200 without reprocessing:

```json
{
  "status": "already_processed",
  "webhook_id": "evt_20240301_001"
}
```

POS systems should use stable, deterministic webhook IDs (e.g., `{event_type}_{pos_order_id}_{timestamp}`) to ensure that retries are correctly deduplicated while genuinely different events are processed.


## Unknown Event Types

Events with an unrecognized `event_type` are acknowledged with 200 but not processed:

```json
{
  "status": "acknowledged",
  "event_type": "inventory.updated",
  "webhook_id": "evt_20240301_003"
}
```

This prevents webhook delivery failures for event types that Arrive does not yet handle, which would cause most POS systems to disable the webhook endpoint after repeated failures.


## Error Responses

| Status Code | Condition                                              |
|------------|--------------------------------------------------------|
| 400        | Invalid JSON body, missing required fields, empty items list |
| 401        | Missing or invalid API key                              |
| 403        | API key lacks `orders:write` permission                 |
| 404        | Order not found (for status update events)              |
| 409        | Invalid state transition, or order changed concurrently  |
| 500        | Internal server error                                    |

**Invalid transition example** (409):

```json
{
  "error": "Invalid transition COMPLETED -> IN_PROGRESS"
}
```


## Rate Limiting

The POS HTTP API Gateway enforces the following throttle limits:

- **Burst limit**: 100 requests
- **Rate limit**: 50 requests per second

These limits apply across all POS API keys. Requests that exceed the limit receive a 429 response from API Gateway.

POS systems should implement exponential backoff when receiving 429 responses. For real-time order tracking, use webhooks rather than polling the list orders endpoint.


## Retry Recommendations

POS systems should retry failed webhook deliveries with the following strategy:

1. Retry on 5xx errors and network timeouts.
2. Do not retry on 4xx errors (except 429, which should use exponential backoff).
3. Use the same `webhook_id` for retries to ensure idempotency.
4. Maximum 5 retry attempts with exponential backoff (1s, 2s, 4s, 8s, 16s).
5. After all retries are exhausted, log the failure and alert operations staff.
