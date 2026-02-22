# 04 - API Reference

Version: 3.0
Last updated: 2026-02-21

## Authentication
### Cognito JWT (default)
Used by users/restaurants/orders services.

### API Key (`X-POS-API-Key`)
Used by `pos-integration` service.

## Orders Service Routes
- `POST /v1/orders`
- `GET /v1/orders/{order_id}`
- `GET /v1/orders/{order_id}/advisory`
- `GET /v1/orders`
- `POST /v1/orders/{order_id}/location`
- `POST /v1/orders/{order_id}/vicinity`
- `POST /v1/orders/{order_id}/cancel`
- `GET /v1/restaurants/{restaurant_id}/orders`
- `POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack`
- `POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status`

### Create Order Request (example)
```json
{
  "restaurant_id": "rest_123",
  "customer_name": "Jane",
  "payment_mode": "PAY_AT_RESTAURANT",
  "items": [
    { "id": "item_1", "name": "Burger", "qty": 1, "price_cents": 1299 }
  ]
}
```

### Arrival Update Request (example)
```json
{
  "event": "AT_DOOR"
}
```

### Location Sample Request (example)
```json
{
  "latitude": 30.2672,
  "longitude": -97.7431,
  "accuracy_m": 12.5,
  "speed_mps": 5.9,
  "sample_time": 1700000000123
}
```

### Restaurant Status Update Request (example)
```json
{
  "status": "IN_PROGRESS"
}
```

## Restaurants Service Routes
- `GET /v1/restaurants/health`
- `GET /v1/restaurants`
- `POST /v1/restaurants`
- `PUT /v1/restaurants/{restaurant_id}`
- `DELETE /v1/restaurants/{restaurant_id}`
- `GET /v1/restaurants/{restaurant_id}/menu`
- `POST /v1/restaurants/{restaurant_id}/menu`
- `GET /v1/restaurants/{restaurant_id}/config`
- `PUT /v1/restaurants/{restaurant_id}/config`
- `POST /v1/restaurants/{restaurant_id}/images/upload-url`
- `GET /v1/favorites`
- `PUT /v1/favorites/{restaurant_id}`
- `DELETE /v1/favorites/{restaurant_id}`

## Users Service Routes
- `GET /v1/users/health` (no auth)
- `GET /v1/users/me`
- `PUT /v1/users/me`
- `POST /v1/users/me/avatar/upload-url`

## POS Integration Routes
- `POST /v1/pos/orders`
- `GET /v1/pos/orders`
- `POST /v1/pos/orders/{order_id}/status`
- `POST /v1/pos/orders/{order_id}/fire`
- `GET /v1/pos/menu`
- `POST /v1/pos/menu/sync`
- `POST /v1/pos/webhook`

## Pagination
Orders list endpoints may return `next_token` for pagination.

### Restaurant Config Fields (Capacity + Dispatch)
`GET/PUT /v1/restaurants/{restaurant_id}/config` includes:
- `max_concurrent_orders`
- `capacity_window_seconds`
- `dispatch_trigger_event` (`5_MIN_OUT` | `PARKING` | `AT_DOOR`)

`dispatch_trigger_event` controls when pending/waiting orders are eligible to move into incoming/dispatch path.
