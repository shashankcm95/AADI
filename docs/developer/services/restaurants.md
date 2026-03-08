# Restaurants Service

The restaurants service manages everything a restaurant needs to exist on the Arrive platform: its profile, menu, configuration, images, geofence boundaries, and customer favorites. It is the second-largest service in the system and the only one that directly interacts with AWS Location Service for geofence management.

All source code lives under `services/restaurants/src/`.


## Architecture Overview

The service runs as a single Lambda function behind an HTTP API Gateway, with one additional Lambda (`geofence_resync_worker.py`) triggered by SQS for asynchronous bulk geofence updates. The main Lambda handles 16 distinct routes spanning restaurant CRUD, menu management, configuration, image uploads, and favorites.

Key source files:

- **app.py** -- Router with the inactive-restaurant gate.
- **handlers/restaurants.py** -- Restaurant CRUD (create, read, update, delete, list) including Cognito user provisioning.
- **handlers/menu.py** -- Menu management with Decimal price handling.
- **handlers/config.py** -- Per-restaurant configuration (capacity, dispatch triggers, POS connections) and global zone configuration.
- **handlers/favorites.py** -- Customer favorites (list, add, remove).
- **handlers/images.py** -- S3 presigned URL generation for restaurant image uploads.
- **utils.py** -- Shared imports hub, geocoding, geofence polygon construction, image URL helpers.
- **geofence_resync_worker.py** -- SQS-triggered Lambda for bulk geofence updates when global zone distances change.


## The Inactive Restaurant Gate

The router in `app.py` implements a global access control gate for restaurant admins whose restaurant is currently inactive. When a `restaurant_admin` user makes a request, the router looks up their assigned restaurant and checks the `active` flag. If the restaurant is inactive, the router blocks all routes except:

- `GET /v1/restaurants` (list, which returns only their own restaurant)
- `GET /v1/restaurants/{restaurant_id}` (read their own profile)
- `PUT /v1/restaurants/{restaurant_id}` (update their own profile)

This gate exists for a specific operational reason: when a restaurant is onboarded, it starts as inactive until an admin activates it. During this setup period, the restaurant admin needs to fill in their profile, upload images, and configure settings. But they should not be able to update their menu, change config, or take any action that implies the restaurant is ready to accept orders.

Critically, the `update_restaurant` handler strips the `active` field from the request body when the caller is not a platform admin. This prevents self-reactivation: a restaurant admin cannot set `active: true` on their own restaurant. Only platform admins can activate or deactivate restaurants.


## Restaurant CRUD

### Create

Restaurant creation (`create_restaurant`) is admin-only. It generates a UUID for the restaurant, geocodes the address using Nominatim, creates both the restaurant record and a config record in DynamoDB, provisions geofences in AWS Location, and optionally creates a Cognito user for the restaurant admin.

The Cognito integration is notable: if a `contact_email` is provided, the handler creates a Cognito user with `custom:role = restaurant_admin` and `custom:restaurant_id` set to the new restaurant's ID. If the user already exists (UsernameExistsException), it updates their attributes instead. The user receives a temporary password via email through Cognito's `DesiredDeliveryMediums: ['EMAIL']`. Email validation uses a strict regex pattern to prevent Cognito filter injection attacks.

### Read

The `get_restaurant` handler supports role-based visibility. Platform admins and the assigned restaurant admin can see all fields including internal ones like `contact_email` and `vicinity_zone`. Customers and unauthenticated users see a redacted view (fields in `PUBLIC_REDACTED_FIELDS` are stripped) and can only see active restaurants. A request for an inactive restaurant by a customer returns 404, not 403, to avoid leaking the existence of restaurants not yet ready for public visibility.

### Update

Updates are permissioned: admins can change anything, restaurant admins can change their own restaurant's profile but not `active` or `rating` fields. The handler detects address changes by comparing the new street/city/state/zip against the existing values and re-geocodes only when something has changed. If geocoding fails, the existing location is preserved rather than being set to null, which would break geofence functionality.

After every update, the handler calls `upsert_restaurant_geofences()` to keep AWS Location in sync. Geofence sync failures are logged as warnings but do not fail the update, because the restaurant profile update is more important than real-time geofence accuracy.

### Delete

Deletion is admin-only and cascading: it removes the restaurant record, config record, all menu versions, associated Cognito user, and geofences. The Cognito cleanup is best-effort (failures are logged but do not block deletion) because the restaurant record is the source of truth.

### List

Restaurant listing has four query paths depending on the caller and filters:

1. **restaurant_admin**: Returns only their own restaurant via direct `get_item`.
2. **admin with no filters**: Full table scan with pagination (up to 200 items per page).
3. **Cuisine filter**: Queries `GSI_Cuisine` index.
4. **Price tier filter**: Queries `GSI_PriceTier` index.
5. **Default (customer)**: Queries `GSI_ActiveRestaurants` index, which only contains active restaurants.

The default path for customers uses a sparse GSI keyed on `is_active = "1"`. When a restaurant is deactivated, the `is_active` attribute is removed (not set to "0"), which automatically removes it from the GSI. This is more efficient than a filter expression because the GSI only contains the rows customers should see.


## Menu Management

Menu handling (`handlers/menu.py`) uses a versioned storage model with a DynamoDB table keyed on `(restaurant_id, menu_version)`. Currently, only the `latest` version is used.

### Decimal Price Handling

Menu prices are stored as Python `Decimal` values with `ROUND_HALF_UP` rounding, and a derived `price_cents` integer field is computed as `int((price * 100).to_integral_value(rounding=ROUND_HALF_UP))`. This two-field approach exists because DynamoDB stores numbers as strings internally and reconstructs them as `Decimal` objects on read, which is precise but inconvenient for frontend consumption. The `price_cents` field gives frontends an integer they can use directly without floating-point arithmetic.

The price parser strips dollar signs and commas from input strings, allowing restaurant admins to paste prices in natural formats like "$12.99" or "1,299". Items without a name or with an unparseable price are collected into an `invalid_items` list and excluded from the saved menu. The response includes the count of skipped items so the caller knows something was wrong, but the valid items are still saved. This partial-success approach prevents one bad item from blocking an entire menu update.

### Item ID Generation

If a menu item does not include an `id` field, the handler generates a UUID for it. This ensures every item has a stable identifier that the orders service can reference, even when the restaurant admin uploads a simple spreadsheet without IDs.


## Geofence System

The geofence system creates three concentric zones around each restaurant, corresponding to the three arrival events:

| Zone    | Event      | Default Radius |
|---------|------------|---------------|
| ZONE_1  | 5_MIN_OUT  | 1500m         |
| ZONE_2  | PARKING    | 150m          |
| ZONE_3  | AT_DOOR    | 30m           |

### Why Three Zones

Three zones provide progressive arrival granularity. ZONE_1 (1500m) gives the restaurant roughly 5 minutes of advance notice. ZONE_2 (150m) indicates the customer is in the immediate vicinity of the restaurant. ZONE_3 (30m) means the customer is at the entrance. Each zone triggers a different arrival event in the orders service, allowing the restaurant to adjust preparation timing.

### Polygon Construction

AWS Location Service requires geofence boundaries as GeoJSON polygons, not circles. The `_build_circle_polygon()` function approximates a circle by computing 12 points (configurable) along the geodesic circumference using the haversine formula. The polygon is closed by repeating the first point at the end, as required by the GeoJSON specification.

The geodesic calculation uses the great-circle distance formula to ensure accuracy at all latitudes. A naive approach using degree offsets would produce ellipses near the poles, but the angular-distance calculation produces geometrically correct circles on the Earth's surface.

### Geofence ID Convention

Each geofence is identified as `{restaurant_id}|{event_name}`, for example `abc-123|5_MIN_OUT`. The orders service's geofence event handler parses this ID to determine which restaurant and which arrival zone the customer entered. The pipe delimiter was chosen over a colon because restaurant IDs are UUIDs that never contain pipes, while colons could appear in URL-encoded values.

### Upsert and Delete

The `upsert_restaurant_geofences()` function creates or updates all three zones in a single `batch_put_geofence` call. Each geofence entry includes properties (`restaurant_id`, `arrival_event`, `arrival_zone`) that are carried through to the EventBridge event, reducing the need for cross-service lookups.

`delete_restaurant_geofences()` removes all three zones when a restaurant is deleted, using `batch_delete_geofence` with the constructed geofence IDs.

### Global Zone Configuration

Zone distances are configurable at the platform level through the global config (`__GLOBAL__` record in the config table). When an admin updates global zone distances, the handler enqueues an SQS message to trigger the geofence resync worker, which iterates through all restaurants and updates their geofences with the new radii.


## Geofence Resync Worker

The resync worker (`geofence_resync_worker.py`) is an SQS-triggered Lambda that performs
bulk geofence updates when global zone distances change. Changing a zone distance from
1500m to 2000m means every restaurant's ZONE_1 geofence needs to be recreated with the
new radius. This cannot happen synchronously in the config update endpoint because a
platform with hundreds of restaurants would timeout the Lambda.

### Batch Processing

The worker processes restaurants in batches (default 25, configurable via
`GEOFENCE_RESYNC_BATCH_SIZE`). For each restaurant in the batch, it calls
`upsert_restaurant_geofences()` with retry logic (up to 3 attempts with exponential
backoff capped at 300ms). This retry logic handles transient AWS Location API errors
without failing the entire batch.

### Pagination via SQS Self-Messaging

If a DynamoDB scan returns `LastEvaluatedKey` (meaning there are more restaurants to
process), the worker enqueues a follow-up SQS message containing the pagination cursor.
The next invocation picks up where the previous one left off. This self-messaging pattern
allows the worker to process an arbitrarily large number of restaurants without exceeding
Lambda's execution time limit.

### State Tracking

Progress is persisted in the global config record (`geofence_sync` field in the
`__GLOBAL__` config item) with the following counters:

- `attempted`: Total restaurants processed across all batches.
- `updated`: Restaurants whose geofences were successfully updated.
- `failed`: Restaurants whose geofences could not be updated after all retries.
- `batches_processed`: Number of SQS messages processed.
- `status`: QUEUED, IN_PROGRESS, COMPLETED, or ENQUEUE_FAILED.

The job ID links the SQS message to the sync state record. If the same message is
reprocessed (SQS at-least-once delivery), the state is loaded and counters are
accumulated rather than reset. When the last batch completes (no more `LastEvaluatedKey`),
the status transitions to COMPLETED.


## Image Uploads

Restaurant images use S3 presigned PUT URLs (`handlers/images.py`). The handler validates the content type (must be `image/*`, SVG is explicitly blocked for security), enforces a maximum of 5 images per restaurant, and generates an S3 key scoped to `restaurants/{restaurant_id}/`. The presigned URL expires after 15 minutes.

The scoping of S3 keys to the restaurant's prefix is a security boundary: it prevents a restaurant admin from overwriting another restaurant's images. The handler verifies this prefix on subsequent profile updates as well, through `_normalize_restaurant_image_keys()` in `utils.py`.


## Restaurant Configuration

The config handler (`handlers/config.py`) manages two levels of configuration:

**Per-restaurant config** includes:
- `max_concurrent_orders` -- How many orders the restaurant can handle simultaneously within a capacity window.
- `capacity_window_seconds` -- Duration of each capacity window (default 300 seconds).
- `dispatch_trigger_zone` / `dispatch_trigger_event` -- Which arrival zone triggers order dispatch.
- `pos_enabled` and `pos_connections` -- POS integration settings with webhook URL validation (HTTPS required) and secret masking.

**Global config** (admin-only) includes:
- `zone_distances_m` -- Default geofence radii for all three zones.
- `zone_labels` -- Human-readable labels for each zone.

POS connection secrets are masked in API responses using `_mask_secret()` (showing only the last 4 characters). When the client sends back a masked secret during an update, the handler detects the `***` prefix and restores the original secret from the database, preventing accidental secret loss.


## Customer Favorites

The favorites subsystem (`handlers/favorites.py`) is intentionally simple: a DynamoDB
table keyed on `(customer_id, restaurant_id)`. The design decisions are:

- **Add favorite**: Verifies the restaurant exists before creating the favorite record.
  This prevents orphan favorites pointing to deleted restaurants. The item includes a
  `created_at` timestamp for display ordering.

- **Remove favorite**: Uses DynamoDB `delete_item`, which is idempotent. Deleting a
  favorite that does not exist succeeds silently. This eliminates race conditions where
  a double-tap on the "unfavorite" button would return an error on the second request.

- **List favorites**: Queries all favorites for the authenticated customer using the
  `customer_id` partition key. The response includes the raw favorite records; restaurant
  details (name, image) are resolved client-side with a separate call to the restaurant
  listing endpoint.

The `_require_customer` helper in `utils.py` enforces that only customer-role users can
manage favorites. Restaurant admins and platform admins cannot add favorites because the
feature is customer-facing and favorites from admin accounts would pollute analytics.


## Geocoding

Address geocoding uses the Nominatim API (OpenStreetMap's geocoding service). The
`geocode_address()` function in `utils.py` implements a two-step strategy:

1. Geocode the full address including unit numbers (e.g., "123 Main St Suite 200, Austin, TX 78701").
2. If that fails, strip the unit/suite/apt number using a regex and retry with the cleaned address.

This retry strategy handles the common case where Nominatim cannot resolve an address
with a unit number but can resolve the building address. The function returns a dict with
`lat` and `lon` as Decimal values, or None if geocoding fails entirely.

Geocoding failures do not block restaurant creation or updates. The restaurant is created
with `location: None`, and geofence creation is skipped. When the address is corrected
in a subsequent update, geocoding runs again and geofences are created retroactively.
