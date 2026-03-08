# API Reference

This document covers every HTTP endpoint exposed by the Arrive platform. Endpoints are grouped by service. All requests and responses use JSON. Every response includes CORS headers.

## Common Conventions

All endpoints under `/v1/orders`, `/v1/restaurants`, `/v1/users`, and `/v1/favorites` require a Cognito JWT bearer token in the `Authorization` header unless otherwise noted. The POS endpoints under `/v1/pos` use API key authentication via the `X-POS-API-Key` header instead.

Error responses follow a consistent format:

```json
{
  "error": "Human-readable error message"
}
```

Standard HTTP status codes are used throughout: `200` for success, `400` for validation errors, `401` for missing or invalid authentication, `403` for authorization failures, `404` for missing resources, `409` for state conflicts, and `500` for internal errors.

Timestamps are Unix epoch seconds (integers). Monetary values are in cents (integers). Quantities are integers.

---

## Orders Service

The orders service manages the full order lifecycle from creation through completion. It exposes 10 routes split between customer-facing and restaurant-facing operations.

### POST /v1/orders

Create a new order.

**Authentication:** Cognito JWT (customer role)

**Headers:**
- `Authorization: Bearer <token>` (required)
- `Idempotency-Key: <uuid>` (recommended)
- `Content-Type: application/json`

**Request Body:**

```json
{
  "restaurant_id": "rest_abc123",
  "items": [
    {
      "id": "item_001",
      "name": "Margherita Pizza",
      "qty": 2,
      "price_cents": 1200,
      "work_units": 3
    }
  ]
}
```

Each item must have an `id` (or legacy `menu_item_id`), a `qty` between 1 and 99, and optionally `price_cents`, `name`, and `work_units`. The `work_units` field (formerly `prep_units`) indicates relative preparation complexity and is used for capacity estimation.

**Response (201):**

```json
{
  "order_id": "ord_xyz789",
  "restaurant_id": "rest_abc123",
  "status": "PENDING_NOT_SENT",
  "items": [...],
  "total_cents": 2400,
  "work_units_total": 6,
  "arrive_fee_cents": 48,
  "created_at": 1700000000,
  "expires_at": 1700003600,
  "receipt_mode": "SOFT",
  "payment_mode": "PAY_AT_RESTAURANT"
}
```

**Errors:**
- `400` if `restaurant_id` is missing or items fail validation
- `409` if idempotency key matches an existing order (returns the existing order)
- `429` if the restaurant is at capacity (returns `WAITING_FOR_CAPACITY` status)

When capacity is full, the order is created with status `WAITING_FOR_CAPACITY` rather than being rejected. The response includes a `suggested_start_at` timestamp indicating when to retry.

### GET /v1/orders/{order_id}

Retrieve a single order by ID.

**Authentication:** Cognito JWT (customer role). The order must belong to the authenticated customer.

**Response (200):**

```json
{
  "order_id": "ord_xyz789",
  "restaurant_id": "rest_abc123",
  "status": "SENT_TO_DESTINATION",
  "items": [...],
  "total_cents": 2400,
  "arrival_status": "5_MIN_OUT",
  "receipt_mode": "SOFT",
  "created_at": 1700000000,
  "sent_at": 1700000120,
  "vicinity": true
}
```

**Errors:**
- `404` if the order does not exist or does not belong to the caller

### GET /v1/orders/{order_id}/advisory

Get a non-binding leave-time advisory for an order. This endpoint checks current capacity usage and recommends when the customer should leave to arrive at an open slot. It does not reserve capacity.

**Authentication:** Cognito JWT (customer role)

**Response (200):**

```json
{
  "recommended_action": "LEAVE_NOW",
  "estimated_wait_seconds": 0,
  "suggested_leave_at": 1700000000,
  "current_window_start": 1700000000,
  "next_window_start": 1700000300,
  "current_reserved": 3,
  "available_slots": 7,
  "max_concurrent": 10,
  "window_seconds": 300,
  "is_estimate": true,
  "advisory_note": "Estimate only. Capacity is reserved only at arrival dispatch."
}
```

The `recommended_action` is either `LEAVE_NOW` (slots available) or `WAIT` (at capacity). When the action is `WAIT`, `suggested_leave_at` indicates the start of the next capacity window.

### GET /v1/orders

List the authenticated customer's orders, sorted by creation time descending.

**Authentication:** Cognito JWT (customer role)

**Query Parameters:**
- `status` (optional) -- filter by order status
- `limit` (optional) -- maximum number of results

**Response (200):**

```json
{
  "orders": [
    {
      "order_id": "ord_xyz789",
      "restaurant_id": "rest_abc123",
      "status": "COMPLETED",
      "total_cents": 2400,
      "created_at": 1700000000
    }
  ]
}
```

### POST /v1/orders/{order_id}/location

Ingest a GPS position for the customer associated with an order. This position is published to the Amazon Location Service tracker for geofence evaluation.

**Authentication:** Cognito JWT (customer role)

**Request Body:**

```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "timestamp": 1700000000
}
```

The `timestamp` field accepts either epoch seconds or epoch milliseconds (the system auto-detects based on magnitude). If omitted, the current server time is used.

**Response (200):**

```json
{
  "published": true,
  "tracker_enabled": true
}
```

If the Location Service tracker is not configured, `tracker_enabled` will be `false` and `published` will be `false`. This is not an error; it means the deployment has not enabled geofencing.

### POST /v1/orders/{order_id}/vicinity

Report an arrival event for the customer. This is the primary dispatch mechanism: when the customer enters the restaurant's vicinity, the mobile app sends this event to trigger order dispatch.

**Authentication:** Cognito JWT (customer role)

**Request Body:**

```json
{
  "event": "5_MIN_OUT",
  "vicinity": true
}
```

Valid event values are `5_MIN_OUT`, `PARKING`, `AT_DOOR`, and `EXIT_VICINITY`. The `vicinity` field must be `true` to trigger dispatch.

**Response (200):**

```json
{
  "session_id": "ord_xyz789",
  "status": "SENT_TO_DESTINATION"
}
```

When the order was `PENDING_NOT_SENT` and capacity is available, the status transitions to `SENT_TO_DESTINATION`. If capacity is full, the status becomes `WAITING_FOR_CAPACITY` with a `suggested_start_at` in the response.

For `EXIT_VICINITY` events: if the order is in `FULFILLING` status and receipt mode is `SOFT`, the order is automatically completed.

### POST /v1/orders/{order_id}/cancel

Cancel an order. Only orders in `PENDING_NOT_SENT` or `WAITING_FOR_CAPACITY` status can be canceled.

**Authentication:** Cognito JWT (customer role)

**Response (200):**

```json
{
  "session_id": "ord_xyz789",
  "status": "CANCELED",
  "canceled_at": 1700000000
}
```

**Errors:**
- `409` if the order has already been sent or is in a later status
- `404` if the order does not exist

### GET /v1/restaurants/{restaurant_id}/orders

List orders for a restaurant, intended for the restaurant dashboard.

**Authentication:** Cognito JWT (restaurant_admin or admin role). Restaurant admins can only access their own restaurant's orders.

**Query Parameters:**
- `status` (optional) -- filter by status (e.g., `SENT_TO_DESTINATION`, `IN_PROGRESS`)

**Response (200):**

```json
{
  "orders": [
    {
      "order_id": "ord_xyz789",
      "customer_name": "Jane Doe",
      "status": "SENT_TO_DESTINATION",
      "items": [...],
      "total_cents": 2400,
      "arrival_status": "PARKING",
      "created_at": 1700000000,
      "sent_at": 1700000120
    }
  ]
}
```

### POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack

Acknowledge receipt of an order and upgrade it to `HARD` receipt mode. Once acknowledged, the order requires explicit completion rather than auto-completing on `EXIT_VICINITY`.

**Authentication:** Cognito JWT (restaurant_admin or admin role)

**Response (200):**

```json
{
  "session_id": "ord_xyz789",
  "receipt_mode": "HARD",
  "received_at": 1700000150
}
```

**Errors:**
- `409` if the order is not in `SENT_TO_DESTINATION` status
- `404` if the order does not exist or does not belong to this restaurant

### POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status

Update an order's status. This is how the restaurant moves an order through the preparation pipeline.

**Authentication:** Cognito JWT (restaurant_admin or admin role)

**Request Body:**

```json
{
  "status": "IN_PROGRESS"
}
```

Valid transitions follow the state machine: `SENT_TO_DESTINATION` to `IN_PROGRESS` to `READY` to `FULFILLING` to `COMPLETED`. Each transition must follow the allowed sequence; skipping states is not permitted.

**Response (200):**

```json
{
  "session_id": "ord_xyz789",
  "status": "IN_PROGRESS"
}
```

**Errors:**
- `409` if the transition is not allowed from the current status
- `404` if the order does not exist or does not belong to this restaurant

---

## Restaurants Service

The restaurants service manages restaurant profiles, menus, configuration, images, and customer favorites. It exposes 16 routes.

### GET /v1/restaurants/health

Health check endpoint.

**Authentication:** None (open)

**Response (200):**

```json
{
  "status": "healthy"
}
```

### GET /v1/restaurants

List all active restaurants. Supports filtering by cuisine and price tier.

**Authentication:** Cognito JWT (any role)

**Query Parameters:**
- `cuisine` (optional) -- filter by cuisine type
- `price_tier` (optional) -- filter by price tier

**Response (200):**

```json
{
  "restaurants": [
    {
      "restaurant_id": "rest_abc123",
      "name": "Bella Italia",
      "cuisine": "Italian",
      "price_tier": "$$",
      "active": true,
      "address": "123 Main St"
    }
  ]
}
```

### POST /v1/restaurants

Create a new restaurant. Admin only.

**Authentication:** Cognito JWT (admin role)

**Request Body:**

```json
{
  "name": "Bella Italia",
  "cuisine": "Italian",
  "price_tier": "$$",
  "address": "123 Main St",
  "latitude": 37.7749,
  "longitude": -122.4194
}
```

**Response (201):**

```json
{
  "restaurant_id": "rest_abc123",
  "name": "Bella Italia",
  "active": true,
  "created_at": 1700000000
}
```

### GET /v1/restaurants/{restaurant_id}

Retrieve a single restaurant by ID.

**Authentication:** Cognito JWT (any role)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "name": "Bella Italia",
  "cuisine": "Italian",
  "price_tier": "$$",
  "active": true,
  "address": "123 Main St",
  "latitude": 37.7749,
  "longitude": -122.4194
}
```

**Errors:**
- `404` if the restaurant does not exist

### PUT /v1/restaurants/{restaurant_id}

Update a restaurant's profile. Restaurant admins can only update their own restaurant and cannot change the `active` field (to prevent self-reactivation after an admin deactivates them).

**Authentication:** Cognito JWT (restaurant_admin for own restaurant, or admin)

**Request Body:**

```json
{
  "name": "Bella Italia Ristorante",
  "address": "456 Oak Ave"
}
```

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "name": "Bella Italia Ristorante",
  "updated_at": 1700000000
}
```

### DELETE /v1/restaurants/{restaurant_id}

Soft-delete a restaurant (sets `active` to false). Admin only.

**Authentication:** Cognito JWT (admin role)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "deleted": true
}
```

### GET /v1/restaurants/{restaurant_id}/menu

Retrieve the current menu for a restaurant.

**Authentication:** Cognito JWT (any role)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "menu_version": "v_20231115",
  "categories": [
    {
      "name": "Appetizers",
      "items": [
        {
          "id": "item_001",
          "name": "Bruschetta",
          "price_cents": 850,
          "work_units": 1,
          "available": true
        }
      ]
    }
  ]
}
```

### POST /v1/restaurants/{restaurant_id}/menu

Update the restaurant's menu. Replaces the current menu entirely. An empty items array is rejected to prevent accidental menu wipe.

**Authentication:** Cognito JWT (restaurant_admin for own restaurant, or admin)

**Request Body:**

```json
{
  "categories": [
    {
      "name": "Appetizers",
      "items": [
        {
          "id": "item_001",
          "name": "Bruschetta",
          "price_cents": 850,
          "work_units": 1,
          "available": true
        }
      ]
    }
  ]
}
```

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "menu_version": "v_20231115_2",
  "updated": true
}
```

**Errors:**
- `400` if items list is empty (prevents silent menu wipe)

### GET /v1/restaurants/{restaurant_id}/config

Retrieve the restaurant's operational configuration (capacity limits, dispatch settings).

**Authentication:** Cognito JWT (restaurant_admin for own restaurant, or admin)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "max_concurrent_orders": 10,
  "capacity_window_seconds": 300,
  "dispatch_trigger_event": "5_MIN_OUT"
}
```

### PUT /v1/restaurants/{restaurant_id}/config

Update the restaurant's operational configuration.

**Authentication:** Cognito JWT (restaurant_admin for own restaurant, or admin)

**Request Body:**

```json
{
  "max_concurrent_orders": 15,
  "capacity_window_seconds": 300,
  "dispatch_trigger_event": "PARKING"
}
```

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "updated": true
}
```

### GET /v1/admin/global-config

Retrieve platform-wide configuration. Admin only.

**Authentication:** Cognito JWT (admin role)

**Response (200):**

```json
{
  "default_max_concurrent_orders": 10,
  "default_capacity_window_seconds": 300,
  "platform_fee_percent": 2.0
}
```

### PUT /v1/admin/global-config

Update platform-wide configuration. Admin only.

**Authentication:** Cognito JWT (admin role)

**Request Body and Response:** Same structure as GET.

### POST /v1/restaurants/{restaurant_id}/images/upload-url

Generate a presigned S3 URL for uploading a restaurant image.

**Authentication:** Cognito JWT (restaurant_admin for own restaurant, or admin)

**Request Body:**

```json
{
  "content_type": "image/jpeg",
  "file_name": "storefront.jpg"
}
```

**Response (200):**

```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "image_key": "rest_abc123/storefront.jpg"
}
```

### GET /v1/favorites

List the authenticated customer's favorite restaurants.

**Authentication:** Cognito JWT (customer role)

**Response (200):**

```json
{
  "favorites": [
    {
      "restaurant_id": "rest_abc123",
      "added_at": 1700000000
    }
  ]
}
```

### PUT /v1/favorites/{restaurant_id}

Add a restaurant to the customer's favorites.

**Authentication:** Cognito JWT (customer role)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "added": true
}
```

### DELETE /v1/favorites/{restaurant_id}

Remove a restaurant from the customer's favorites.

**Authentication:** Cognito JWT (customer role)

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "removed": true
}
```

---

## Users Service

The users service manages user profiles and avatar uploads. It exposes 4 routes.

### GET /v1/users/health

Health check endpoint.

**Authentication:** None (open)

**Response (200):**

```json
{
  "status": "healthy",
  "service": "users"
}
```

### GET /v1/users/me

Retrieve the authenticated user's profile.

**Authentication:** Cognito JWT (any role)

**Response (200):**

```json
{
  "user_id": "sub_abc123",
  "email": "jane@example.com",
  "name": "Jane Doe",
  "phone": "+15551234567",
  "picture": "https://cdn.example.com/avatars/sub_abc123/photo.jpg",
  "role": "customer",
  "created_at": 1700000000
}
```

**Errors:**
- `404` if no profile exists for the authenticated user

### PUT /v1/users/me

Update the authenticated user's profile. Only the `name` and `phone` fields can be updated by the user. The `picture` field is updated indirectly through the avatar upload flow.

**Authentication:** Cognito JWT (any role)

**Request Body:**

```json
{
  "name": "Jane Smith",
  "phone": "+15559876543"
}
```

**Response (200):**

```json
{
  "user_id": "sub_abc123",
  "name": "Jane Smith",
  "phone": "+15559876543",
  "updated_at": 1700000000
}
```

### POST /v1/users/me/avatar/upload-url

Generate a presigned S3 URL for uploading the user's avatar. The S3 key is scoped to the user's ID to prevent uploading to arbitrary paths.

**Authentication:** Cognito JWT (any role)

**Request Body:**

```json
{
  "content_type": "image/jpeg"
}
```

**Response (200):**

```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "avatar_key": "sub_abc123/avatar.jpg"
}
```

---

## POS Integration Service

The POS integration service allows external point-of-sale systems to interact with the Arrive platform. All 7 routes require API key authentication via the `X-POS-API-Key` header. Each API key is bound to a specific restaurant and carries a set of permissions.

### POST /v1/pos/orders

Create an order from the POS system.

**Authentication:** API key with `orders:write` permission

**Request Body:**

```json
{
  "customer_name": "Walk-in Customer",
  "items": [
    {
      "id": "item_001",
      "name": "Burger",
      "qty": 1,
      "price_cents": 1500,
      "work_units": 2
    }
  ]
}
```

**Response (201):**

```json
{
  "order_id": "ord_pos_abc",
  "restaurant_id": "rest_abc123",
  "status": "PENDING_NOT_SENT",
  "created_at": 1700000000
}
```

### GET /v1/pos/orders

List orders for the restaurant associated with the API key.

**Authentication:** API key with `orders:read` permission

**Query Parameters:**
- `status` (optional) -- filter by order status

**Response (200):**

```json
{
  "orders": [...]
}
```

### POST /v1/pos/orders/{order_id}/status

Update an order's status from the POS system.

**Authentication:** API key with `orders:write` permission

**Request Body:**

```json
{
  "status": "IN_PROGRESS"
}
```

**Response (200):**

```json
{
  "order_id": "ord_pos_abc",
  "status": "IN_PROGRESS"
}
```

### POST /v1/pos/orders/{order_id}/fire

Force-fire an order, bypassing the normal dispatch flow. This transitions the order directly to `SENT_TO_DESTINATION` status regardless of vicinity.

**Authentication:** API key with `orders:write` permission

**Response (200):**

```json
{
  "order_id": "ord_pos_abc",
  "status": "SENT_TO_DESTINATION",
  "fired": true
}
```

### GET /v1/pos/menu

Retrieve the restaurant's current menu.

**Authentication:** API key with `menu:read` permission

**Response (200):**

```json
{
  "restaurant_id": "rest_abc123",
  "categories": [...]
}
```

### POST /v1/pos/menu/sync

Sync the menu from the POS system to Arrive. This replaces the current menu. An empty items payload is rejected to prevent accidental menu deletion.

**Authentication:** API key with `menu:write` permission

**Request Body:**

```json
{
  "categories": [
    {
      "name": "Main Course",
      "items": [
        {
          "id": "pos_item_001",
          "name": "Steak",
          "price_cents": 3500,
          "work_units": 5,
          "available": true
        }
      ]
    }
  ]
}
```

**Response (200):**

```json
{
  "synced": true,
  "restaurant_id": "rest_abc123"
}
```

### POST /v1/pos/webhook

Generic webhook endpoint for POS system events. The POS system can send order-related events (payment confirmed, ticket voided, etc.) through this endpoint. Because webhook events can create or update orders, this route requires `orders:write` permission.

**Authentication:** API key with `orders:write` permission

**Request Body:** Varies by POS system. The handler parses the event type and dispatches accordingly.

**Response (200):**

```json
{
  "accepted": true,
  "webhook_id": "wh_abc123"
}
```

Webhooks are idempotent: duplicate webhook IDs are rejected with a `200` response indicating the event was already processed.
