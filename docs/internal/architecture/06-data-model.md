# 06 - Data Model

Version: 3.0
Last updated: 2026-02-21

## Orders Domain Tables
### OrdersTable
Primary key:
- `order_id` (HASH)

GSIs:
- `GSI_RestaurantStatus`: (`restaurant_id`, `status`)
- `GSI_CustomerOrders`: (`customer_id`, `created_at`)

Representative attributes:
- identity: `order_id`, `session_id`, `restaurant_id`, `destination_id`, `customer_id`
- lifecycle: `status`, `arrival_status`, `created_at`, `updated_at`, `sent_at`, `expires_at`
- timing/capacity: `capacity_window_start`, `waiting_since`, `suggested_start_at`
- payload: `items[]`, `total_cents`, `work_units_total`, `arrive_fee_cents`, `payment_mode`
- receipt: `receipt_mode`, `received_at`, `received_by_destination`
- telemetry: `last_location_lat`, `last_location_lon`, `last_location_sample_time`, `last_location_received_at`
- geofence shadow: `geofence_shadow_last_event`, `geofence_shadow_last_event_id`, `geofence_shadow_last_received_at`
- retention: `ttl`

### CapacityTable
Primary key:
- `restaurant_id` (HASH)
- `window_start` (RANGE)

Attributes:
- `current_count`
- `ttl`

### IdempotencyTable
Primary key:
- `idempotency_key` (HASH)

Attributes:
- `status` (`PROCESSING` / `COMPLETED`)
- `body`
- `created_at`
- `ttl`

### GeofenceEventsTable
Primary key:
- `event_id` (HASH)

Attributes:
- `created_at`
- `ttl`

## Restaurants Domain Tables
### RestaurantsTable
Primary key:
- `restaurant_id`

GSIs:
- `GSI_ActiveRestaurants`: (`is_active`, `name`)
- `GSI_Cuisine`: (`cuisine`, `name`)
- `GSI_PriceTier`: (`price_tier`, `name`)

### MenusTable
Composite key:
- `restaurant_id`
- `menu_version` (uses `latest`)

### RestaurantConfigTable
Primary key:
- `restaurant_id`

Attributes include:
- `max_concurrent_orders`
- `capacity_window_seconds`
- `pos_enabled`
- `pos_connections[]`

### FavoritesTable
Composite key:
- `customer_id`
- `restaurant_id`

## Users Domain
### UsersTable
Primary key:
- `user_id`

Attributes include:
- `email`, `role`, `name`, `phone_number`, `picture`, timestamps

## POS Integration Domain
### PosApiKeysTable
Primary key:
- `api_key`

### PosWebhookLogsTable
Primary key:
- `webhook_id`
