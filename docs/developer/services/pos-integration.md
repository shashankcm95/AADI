# POS Integration Service

The POS (Point of Sale) integration service is the bridge between external restaurant POS systems and the Arrive platform. It allows POS systems to push orders into Arrive, pull order status, sync menus, force-fire orders, and receive webhook notifications. Unlike the other services that authenticate through Cognito JWTs, the POS service uses API key authentication because POS systems are server-to-server integrations that cannot participate in OAuth flows.

All source code lives under `services/pos-integration/src/`.


## Architecture Overview

The service runs as a single Lambda function behind a dedicated HTTP API Gateway with throttling enabled (burst 100, rate 50 requests per second). The throttle limits exist because POS systems poll for order status and a misconfigured polling interval could generate significant load.

Key source files:

- **app.py** -- Router. Authenticates every request via API key, checks permissions, dispatches to handlers.
- **auth.py** -- API key validation with SHA-256 hashing and DynamoDB lookup.
- **handlers.py** -- All seven handler functions: create order, list orders, update status, force fire, get menu, sync menu, webhook.
- **pos_mapper.py** -- Format conversion between POS-native payloads and Arrive's domain model.


## API Key Authentication

### Why Not Cognito

POS integrations are machine-to-machine. A Toast or Square POS terminal does not have a user session, cannot open a browser for OAuth consent, and cannot refresh tokens. API keys are the standard authentication mechanism for this type of integration. The key is included in the `X-POS-API-Key` HTTP header on every request.

### SHA-256 Hashing

API keys are never stored in plaintext. When a key is provisioned, its SHA-256 hex digest is computed and stored as the partition key in the `POS_API_KEYS_TABLE`. When a request arrives, the handler hashes the incoming key and looks up the hash in DynamoDB. If the hash matches, the associated key record is returned.

This design provides several security benefits:

1. **Database breach resilience**: If the DynamoDB table is leaked, the attacker gets hashes, not usable keys. SHA-256 is a one-way function; the original key cannot be recovered.
2. **No encryption key management**: Unlike symmetric encryption, hashing does not require managing encryption keys or key rotation schedules.
3. **Constant-time lookup**: The hash is used as the DynamoDB partition key, so lookup is O(1) regardless of how many keys exist.

The tradeoff is that a lost key cannot be recovered -- it must be re-provisioned. This is acceptable because POS integrations are configured by restaurant admins or platform staff, not end users.

### Key Record Structure

Each key record in DynamoDB contains:

- `api_key` (PK): SHA-256 hash of the raw key.
- `restaurant_id`: The restaurant this key grants access to.
- `pos_system`: Identifier for the POS provider (toast, square, clover, custom, generic).
- `permissions`: List of permission strings.
- `ttl`: Optional expiry timestamp. If present and in the past, the key is treated as invalid.

The `pos_system` field is not just metadata -- it drives format conversion in the mapper module.


## Permission System

Permissions use a `resource:action` format with four defined permissions:

| Permission     | Grants Access To                              |
|---------------|-----------------------------------------------|
| `orders:read`  | List orders for the restaurant                |
| `orders:write` | Create orders, update status, force fire, webhook |
| `menu:read`    | Read the restaurant's menu                     |
| `menu:write`   | Push menu updates from POS to Arrive           |

A wildcard permission (`*`) grants all access. Permissions are checked per route in the router, not in individual handlers. If the key lacks the required permission, the router returns 403 before the handler is invoked.

The permission model is fail-closed: if the `permissions` field is missing from the key record, it defaults to an empty list, granting no access. This is deliberate. A key provisioned without explicit permissions is useless, which forces the admin to think about what access the POS system actually needs.

### Webhook Route Permission

The webhook endpoint requires `orders:write` permission even though webhooks might seem like a read operation from the POS perspective. The reason is that webhook events can trigger order creation (`order.created`) and status updates (`order_status.changed`), which are write operations on the Arrive side. A key with only `menu:read` permission should not be able to create orders through the webhook.


## Webhook Idempotency

The webhook handler (`handle_webhook`) must be idempotent because POS systems may retry failed webhook deliveries. Idempotency is implemented using the `PosWebhookLogsTable`:

1. Extract the `webhook_id` (or `event_id`) from the payload. If missing, generate one and log a warning.
2. Attempt to write the webhook record with `attribute_not_exists(webhook_id)` as the condition.
3. If the write succeeds, this is a new event -- process it.
4. If the write fails with `ConditionalCheckFailedException`, this is a duplicate -- return 200 with `status: already_processed`.

The deduplication window is 7 days (TTL on the webhook log records). This is long enough to cover any reasonable retry policy while preventing the table from growing indefinitely.

### Event Routing

The webhook handler routes by `event_type`:

- `order.created` and `order.placed` -- Delegated to `handle_create_order`.
- `order.updated` and `order_status.changed` -- Delegated to `handle_update_status`.
- Unknown event types -- Acknowledged with 200 but not processed. This prevents webhook delivery failures for event types Arrive does not yet support, which would cause POS systems to disable the webhook entirely.


## POS-to-Arrive Format Mapper

The `pos_mapper.py` module handles the translation between POS-native data formats and Arrive's domain model. This isolation is important because each POS system uses different field names, nesting structures, and data types.

### Inbound Mapping (POS to Arrive)

The `pos_order_to_session()` function dispatches to POS-specific mappers:

- **Toast**: Orders contain `checks` with `selections`. Prices are in dollars (floats), converted to cents via `int(round(price * 100))`. Item IDs come from the `guid` field.
- **Square**: Orders contain `line_items`. Prices are already in cents in the `base_price_money.amount` field. Item IDs come from `catalog_object_id`.
- **Generic**: A pass-through mapper that expects items in a simplified format with `id`, `name`, `qty`, and `price_cents`.

All mappers normalize to the same output format: a dict with `restaurant_id`, `items` (list of `{id, name, qty, price_cents, work_units}`), `customer_name`, and `pos_order_ref`.

The `restaurant_id` from the mapper output is overridden by the `restaurant_id` from the API key record. This is a security measure: even if the POS payload claims a different restaurant, the key's binding takes precedence. A POS key can only create orders for its own restaurant.

### Outbound Mapping (Arrive to POS)

The `session_to_pos_order()` function converts Arrive sessions into a POS-friendly format. It strips internal fields (like `capacity_window_start`, `ttl`, `geofence_shadow_last_event`) and renames fields to POS conventions (e.g., `order_id` becomes `arrive_order_id`, `qty` becomes `quantity`).

### Menu Mapping

The `pos_menu_to_resources()` function converts POS menu items into Arrive's resource format. It handles the field name variations across POS systems (`id` vs `external_id` vs `guid`, `price_cents` vs `price`, `work_units` vs `prep_time_minutes`).


## Status Mapping

POS systems use their own status vocabulary. The `_STATUS_MAP` dictionary translates between them:

| POS Status    | Arrive Status          |
|--------------|------------------------|
| PREPARING    | IN_PROGRESS            |
| READY        | READY                  |
| PICKED_UP    | FULFILLING             |
| COMPLETED    | COMPLETED              |

The mapper also accepts Arrive-native statuses passthrough, so a POS system that has already adopted Arrive's terminology does not need a separate code path.

### Transition Validation

Status updates go through `_validate_transition()`, which enforces the same linear state machine as the orders engine:

```
SENT_TO_DESTINATION -> IN_PROGRESS -> READY -> FULFILLING -> COMPLETED
```

Additionally, it allows PENDING and WAITING orders to transition directly to SENT (for force-fire scenarios). Idempotent updates (same status as current) are accepted without error. Invalid transitions return 409 with a descriptive error message.


## Force Fire

The force-fire endpoint (`POST /v1/pos/orders/{order_id}/fire`) allows restaurant staff to manually dispatch an order that is waiting for the customer's arrival signal. This is the POS equivalent of a customer pressing "I'm Here" -- it transitions PENDING_NOT_SENT or WAITING_FOR_CAPACITY orders directly to SENT_TO_DESTINATION.

Force fire exists because real-world restaurant operations cannot always wait for GPS signals. A regular customer who walks in and orders at the counter has no mobile app sending location data. The POS integration allows the kitchen to start preparing when they see the customer, regardless of the Arrive arrival detection pipeline.

The force-fire update sets `vicinity: True`, `receipt_mode: HARD`, and `sent_at` to the current timestamp. The HARD receipt mode indicates that the restaurant explicitly acknowledged the order, which prevents the auto-complete-on-EXIT_VICINITY logic from closing the order prematurely.

Force fire uses the same conditional update guard as regular status updates (`ConditionExpression` checking both `restaurant_id` and current status) to prevent race conditions.


## Menu Sync

The menu sync endpoint (`POST /v1/pos/menu/sync`) is disabled by default, controlled by the `POS_MENU_SYNC_ENABLED` environment variable. When disabled, it returns 409 with a message directing the user to the restaurant admin CSV ingestion flow.

The feature is disabled by default because menu sync from a POS system can overwrite carefully curated menus. A restaurant admin might have added images, descriptions, and categories through the admin portal that would be lost if the POS blindly pushed its simpler menu format. Enabling this feature is a deliberate opt-in per deployment.

When enabled, the handler validates that the `items` list is non-empty (preventing accidental menu wipeout), converts the POS format to Arrive resources via `pos_menu_to_resources()`, and writes the result to the menus table as the `latest` version.


## Order Creation from POS

When a POS creates an order (`handle_create_order`), it follows a similar flow to the customer-facing order creation but with key differences:

- The order ID is prefixed with `ord_pos_` to distinguish POS-originated orders from customer-originated ones.
- There is no idempotency key check (POS systems use webhooks with their own deduplication).
- There is no capacity reservation at creation time (POS orders are dispatched via force-fire when the restaurant is ready).
- The Arrive platform fee is calculated at 2% of the order total, split between restaurant and customer.

The `pos_order_ref` field links the Arrive order back to the POS system's internal order ID, enabling bi-directional lookup.


## Order Listing for POS

The `handle_list_orders` handler returns orders in POS-friendly format via
`session_to_pos_order()`. It queries `GSI_RestaurantStatus` using the restaurant_id from
the API key record, with an optional `status` query parameter for filtering.

The response format strips internal Arrive fields and uses POS-standard naming:

- `arrive_order_id` instead of `order_id`
- `quantity` instead of `qty`
- `external_id` instead of `id` (in items)

This translation ensures POS systems receive a consistent, documented schema regardless
of how Arrive's internal model evolves.


## Cross-Service Table Access

The POS integration service reads and writes to tables owned by other services:

- **OrdersTable**: Created by the orders service. POS creates orders, updates statuses.
- **MenusTable**: Created by the restaurants service. POS reads and optionally syncs menus.
- **CapacityTable**: Created by the orders service. POS releases slots on completion.
- **PosWebhookLogsTable**: Owned by POS. Stores webhook deduplication records.
- **POS_API_KEYS_TABLE**: Owned by POS. Stores hashed API keys.

This cross-service table access is a pragmatic decision. Creating separate order tables
for POS-originated vs customer-originated orders would require the restaurant dashboard
to query two tables, duplicating logic and creating consistency challenges. By writing
directly to the shared OrdersTable, POS orders appear alongside customer orders in all
restaurant-facing views.


## Throttling

The HTTP API Gateway is configured with `burst: 100` and `rate: 50` requests per second.
These limits apply across all POS integrations (not per-key) and exist to protect the
backend DynamoDB tables from excessive read/write throughput. A POS system that polls
every second for 50 restaurants would consume the entire rate limit, so POS integrations
are expected to use webhooks for real-time updates and polling only as a fallback.

When the rate limit is exceeded, API Gateway returns 429 (Too Many Requests). POS systems
should implement exponential backoff on 429 responses. The burst limit of 100 allows short
spikes (e.g., a webhook batch from a POS system processing end-of-day settlements) without
triggering throttling, while the sustained rate of 50 rps prevents prolonged overload.
