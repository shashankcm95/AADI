# Data Model

Every piece of persistent state in the Arrive platform lives in DynamoDB. There are no relational databases, no Redis caches, and no file-based storage (apart from S3 for binary assets like images and avatars). This document describes every DynamoDB table, its key schema, global secondary indexes, TTL configuration, and the access patterns that drive its design.

## Design Philosophy

The tables are designed around access patterns, not entity relationships. Each table's key schema and indexes are chosen to serve the specific queries that the application needs, rather than to normalize data. This means some data is denormalized across tables, and some tables exist solely to support a single query pattern (like `IdempotencyTable` for deduplication or `GeofenceEventsTable` for event claiming).

All tables have Point-in-Time Recovery (PITR) enabled for operational safety. Tables that hold transient data (capacity slots, idempotency records, geofence events) also use DynamoDB TTL to automatically expire old rows and control costs.

## OrdersTable

The OrdersTable is the central table of the platform. It stores every order from creation through completion.

**Key Schema:**
- Partition Key: `order_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| order_id | S | Primary identifier, generated at creation |
| restaurant_id | S | The restaurant this order is for |
| customer_id | S | Cognito `sub` of the ordering customer |
| status | S | Current lifecycle status (see Order Lifecycle) |
| items | L | List of ordered items with id, name, qty, price_cents, work_units |
| total_cents | N | Total order value in cents |
| work_units_total | N | Sum of work_units across all items |
| arrive_fee_cents | N | Platform fee in cents |
| tip_cents | N | Tip amount in cents (default 0) |
| receipt_mode | S | SOFT or HARD |
| payment_mode | S | PAY_AT_RESTAURANT |
| vicinity | BOOL | Whether customer is in the restaurant vicinity |
| arrival_status | S | Latest arrival event (5_MIN_OUT, PARKING, AT_DOOR, EXIT_VICINITY) |
| customer_name | S | Display name for the restaurant dashboard |
| created_at | N | Creation timestamp (epoch seconds) |
| expires_at | N | Expiry timestamp for PENDING/WAITING orders |
| sent_at | N | When the order was dispatched to the restaurant |
| started_at | N | When IN_PROGRESS began |
| ready_at | N | When READY was set |
| fulfilling_at | N | When FULFILLING began |
| completed_at | N | When COMPLETED was set |
| canceled_at | N | When CANCELED was set |
| capacity_window_start | N | The capacity window this order reserved a slot in |
| waiting_since | N | When WAITING_FOR_CAPACITY began |
| suggested_start_at | N | Next capacity window start (for WAITING orders) |
| received_by_destination | BOOL | Whether the restaurant has acknowledged the order |
| received_at | N | When the restaurant acknowledged |
| ttl | N | DynamoDB TTL attribute (epoch seconds) |

**Global Secondary Indexes:**

**GSI_RestaurantStatus** enables the restaurant dashboard to list orders by status.
- Partition Key: `restaurant_id` (S)
- Sort Key: `status` (S)
- Projection: ALL
- Used by: `list_restaurant_orders` handler to fetch active orders for a restaurant filtered by status.

**GSI_RestaurantCreated** enables the restaurant to list orders sorted by creation time.
- Partition Key: `restaurant_id` (S)
- Sort Key: `created_at` (N)
- Projection: ALL
- Used by: restaurant order history queries sorted chronologically.

**GSI_CustomerOrders** enables the customer to list their own orders sorted by creation time.
- Partition Key: `customer_id` (S)
- Sort Key: `created_at` (N)
- Projection: ALL
- Used by: `list_customer_orders` handler, and the geofence event handler to find a customer's active order at a restaurant.

**GSI_StatusExpiry** enables the expiry Lambda to find orders that should be expired.
- Partition Key: `status` (S)
- Sort Key: `expires_at` (N)
- Projection: ALL
- Used by: `expire_orders.py` Lambda. Queries for `status = PENDING_NOT_SENT` and `status = WAITING_FOR_CAPACITY` where `expires_at < now`.

**TTL:** Enabled on the `ttl` attribute. Orders are given a TTL beyond their expiry window so that completed, canceled, and expired orders are eventually cleaned up.

**Writer:** Orders service (exclusive).
**Readers:** Orders service, POS integration service (via shared DynamoDB reads for order lookups).

## CapacityTable

The CapacityTable tracks how many orders are currently active within each time window for each restaurant. It is the enforcement mechanism for capacity gating.

**Key Schema:**
- Partition Key: `restaurant_id` (String)
- Sort Key: `window_start` (Number)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| restaurant_id | S | The restaurant (destination) ID |
| window_start | N | Epoch seconds, floored to window boundary |
| current_count | N | Number of currently reserved slots |
| ttl | N | DynamoDB TTL, set to window_start + window_seconds + 3600 |

**TTL:** Enabled on `ttl`. Capacity rows expire roughly one hour after their window closes, keeping the table compact.

**Writer:** Orders service (atomic increment on dispatch, atomic decrement on cancel/complete).
**Readers:** Orders service (advisory endpoint reads current usage; dispatch handler reserves slots).

The `try_reserve_slot` function uses DynamoDB's atomic counter pattern with a conditional expression: it increments `current_count` only if the current value is less than `max_concurrent_orders` or if the attribute does not exist. This provides strongly consistent capacity enforcement without distributed locks.

## IdempotencyTable

The IdempotencyTable prevents duplicate order creation from retried requests.

**Key Schema:**
- Partition Key: `idempotency_key` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| idempotency_key | S | The client-provided UUID from the Idempotency-Key header |
| order_id | S | The order ID created for this key |
| created_at | N | When the idempotency record was created |
| ttl | N | DynamoDB TTL, typically 24 hours after creation |

**TTL:** Enabled on `ttl`. Records expire after approximately 24 hours, allowing the same idempotency key to be reused after that window.

**Writer:** Orders service.
**Readers:** Orders service (checked before order creation).

## GeofenceEventsTable

The GeofenceEventsTable deduplicates EventBridge geofence events. Amazon Location Service can deliver the same ENTER event multiple times, and this table ensures each event is processed exactly once.

**Key Schema:**
- Partition Key: `event_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| event_id | S | The EventBridge event ID |
| created_at | N | When the event was claimed |
| ttl | N | DynamoDB TTL, 7 days after creation |

**TTL:** Enabled on `ttl`. Events expire after 7 days.

**Writer:** Orders service (geofence events handler).
**Readers:** Orders service (geofence events handler checks for existing events before processing).

The deduplication uses a conditional put: `attribute_not_exists(event_id)`. If the put succeeds, this is the first time the event has been seen. If it fails with `ConditionalCheckFailedException`, the event is a duplicate and is silently ignored.

## RestaurantsTable

The RestaurantsTable stores restaurant profiles.

**Key Schema:**
- Partition Key: `restaurant_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| restaurant_id | S | Primary identifier |
| name | S | Restaurant display name |
| cuisine | S | Cuisine type (Italian, Mexican, etc.) |
| price_tier | S | Price tier ($, $$, $$$) |
| address | S | Street address |
| latitude | N | GPS latitude |
| longitude | N | GPS longitude |
| active | BOOL | Whether the restaurant is active and visible |
| created_at | N | Creation timestamp |
| updated_at | N | Last update timestamp |

**Global Secondary Indexes:**

**GSI_ActiveRestaurants** enables listing all active restaurants sorted by name.
- Partition Key: `is_active` (S) -- string representation of the active flag
- Sort Key: `name` (S)
- Projection: ALL
- Used by: `list_restaurants` handler for the default restaurant listing.

**GSI_Cuisine** enables filtering restaurants by cuisine.
- Partition Key: `cuisine` (S)
- Sort Key: `name` (S)
- Projection: ALL
- Used by: `list_restaurants` handler when a cuisine filter is specified.

**GSI_PriceTier** enables filtering restaurants by price tier.
- Partition Key: `price_tier` (S)
- Sort Key: `name` (S)
- Projection: ALL
- Used by: `list_restaurants` handler when a price tier filter is specified.

**Writer:** Restaurants service (exclusive).
**Readers:** Restaurants service, and the restaurants service router reads a restaurant's `active` flag to enforce the inactive restaurant gate for restaurant_admin users.

## RestaurantConfigTable

The RestaurantConfigTable stores per-restaurant operational settings, primarily capacity configuration.

**Key Schema:**
- Partition Key: `restaurant_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| restaurant_id | S | Restaurant this config belongs to |
| max_concurrent_orders | N | Maximum orders per capacity window (default: 10) |
| capacity_window_seconds | N | Duration of each capacity window in seconds (default: 300) |
| dispatch_trigger_event | S | Arrival event that triggers dispatch (default: 5_MIN_OUT) |

**Writer:** Restaurants service (via config update handler).
**Readers:** Orders service (reads capacity config during dispatch and advisory calculations).

This is a cross-service read: the Restaurants service writes the configuration, and the Orders service reads it. There is no synchronous inter-service call; both services access the same DynamoDB table directly.

## MenusTable

The MenusTable stores restaurant menus with versioning.

**Key Schema:**
- Partition Key: `restaurant_id` (String)
- Sort Key: `menu_version` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| restaurant_id | S | Restaurant this menu belongs to |
| menu_version | S | Version identifier (e.g., v_20231115) |
| categories | L | List of category objects, each containing items |
| created_at | N | When this menu version was created |
| updated_at | N | Last modification timestamp |

**Writer:** Restaurants service, POS integration service (via menu sync).
**Readers:** Restaurants service, POS integration service.

The sort key on `menu_version` allows querying for the latest version by sorting descending and limiting to 1 result. Historical menu versions are retained for audit purposes.

## FavoritesTable

The FavoritesTable stores customer-restaurant favorites relationships.

**Key Schema:**
- Partition Key: `customer_id` (String)
- Sort Key: `restaurant_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| customer_id | S | Cognito sub of the customer |
| restaurant_id | S | The favorited restaurant |
| added_at | N | When the favorite was added |

**Writer:** Restaurants service (favorites handler).
**Readers:** Restaurants service (favorites handler).

The composite key supports two access patterns: listing all favorites for a customer (query on `customer_id`), and checking whether a specific restaurant is a favorite (get item with both keys).

## PosApiKeysTable

The PosApiKeysTable stores API keys for POS system authentication. Keys are stored as SHA-256 hashes; the raw plaintext is never persisted.

**Key Schema:**
- Partition Key: `api_key` (String) -- SHA-256 hex digest of the raw API key

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| api_key | S | SHA-256 hash of the raw API key |
| restaurant_id | S | Restaurant this key is bound to |
| pos_system | S | POS system identifier (e.g., "square", "toast", "generic") |
| permissions | L | List of permission strings (e.g., ["orders:read", "orders:write"]) |
| created_at | N | When the key was provisioned |
| ttl | N | DynamoDB TTL for key expiration |

**TTL:** Enabled on `ttl`. Keys can be given an expiration date.

**Writer:** Administrative process (key provisioning is not exposed via API).
**Readers:** POS integration service (validates keys on every request).

When a POS request arrives, the `validate_key` function computes `sha256(raw_key)` and performs a `get_item` lookup. If the item exists and has not expired (TTL check in application code), the key is valid and the attached `restaurant_id` and `permissions` are returned.

## PosWebhookLogsTable

The PosWebhookLogsTable logs and deduplicates incoming POS webhook events.

**Key Schema:**
- Partition Key: `webhook_id` (String)

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| webhook_id | S | Unique identifier for the webhook event |
| restaurant_id | S | Restaurant the webhook relates to |
| event_type | S | Type of POS event |
| payload | M | Raw webhook payload |
| processed_at | N | When the webhook was processed |
| ttl | N | DynamoDB TTL |

**TTL:** Enabled on `ttl`. Webhook logs expire after a retention period.

**Writer:** POS integration service.
**Readers:** POS integration service (deduplication check before processing).

## UsersTable

The UsersTable stores user profiles.

**Key Schema:**
- Partition Key: `user_id` (String) -- the Cognito `sub` claim

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| user_id | S | Cognito sub (matches customer_id in orders) |
| email | S | User's email address |
| name | S | Display name |
| phone | S | Phone number |
| picture | S | S3 key for the user's avatar, scoped to user_id prefix |
| role | S | User role (customer, restaurant_admin, admin) |
| restaurant_id | S | For restaurant_admin users, their assigned restaurant |
| created_at | N | Profile creation timestamp |
| updated_at | N | Last profile update timestamp |

**Writer:** Users service (profile updates, avatar URL recording), Cognito PostConfirmation trigger (initial profile creation).
**Readers:** Users service.

The `picture` field is validated to ensure it starts with the user's own `user_id` prefix, preventing users from referencing arbitrary S3 keys.

## Access Pattern Summary

| Pattern | Table | Index | Operation |
|---------|-------|-------|-----------|
| Get order by ID | OrdersTable | Primary | GetItem |
| List customer's orders | OrdersTable | GSI_CustomerOrders | Query |
| List restaurant's orders by status | OrdersTable | GSI_RestaurantStatus | Query |
| List restaurant's orders by time | OrdersTable | GSI_RestaurantCreated | Query |
| Find expired orders | OrdersTable | GSI_StatusExpiry | Query |
| Reserve capacity slot | CapacityTable | Primary | UpdateItem (conditional) |
| Release capacity slot | CapacityTable | Primary | UpdateItem |
| Read capacity usage | CapacityTable | Primary | GetItem |
| Check idempotency | IdempotencyTable | Primary | GetItem / PutItem |
| Claim geofence event | GeofenceEventsTable | Primary | PutItem (conditional) |
| List active restaurants | RestaurantsTable | GSI_ActiveRestaurants | Query |
| Filter by cuisine | RestaurantsTable | GSI_Cuisine | Query |
| Filter by price tier | RestaurantsTable | GSI_PriceTier | Query |
| Get restaurant config | RestaurantConfigTable | Primary | GetItem |
| Get latest menu | MenusTable | Primary | Query (desc, limit 1) |
| List favorites | FavoritesTable | Primary | Query on customer_id |
| Validate POS API key | PosApiKeysTable | Primary | GetItem |
| Deduplicate webhook | PosWebhookLogsTable | Primary | PutItem (conditional) |
| Get user profile | UsersTable | Primary | GetItem |
