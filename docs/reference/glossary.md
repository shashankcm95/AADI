# Glossary

This glossary defines every domain term, status value, abbreviation, and technical concept used in the Arrive platform. Entries are organized alphabetically.

---

**5_MIN_OUT** -- An arrival event indicating the customer is approximately five minutes away from the restaurant. This is the default dispatch trigger event: when the system receives a 5_MIN_OUT event and capacity is available, the order transitions from PENDING_NOT_SENT to SENT_TO_DESTINATION.

**Acknowledgment (Ack)** -- The act of a restaurant confirming receipt of an order. When a restaurant acknowledges an order via the `ack` endpoint, the receipt mode upgrades from SOFT to HARD, requiring explicit completion rather than auto-completion on EXIT_VICINITY.

**Admin** -- A platform-wide administrator role. Admins can create and delete restaurants, manage global configuration, and access any restaurant's data. The role is stored as `custom:role = admin` in the Cognito JWT.

**API Key** -- A secret string used by POS systems to authenticate with the POS Integration service. The raw key is never stored; only its SHA-256 hash is persisted in the PosApiKeysTable. API keys are bound to a specific restaurant and carry a permissions array.

**Arrive Fee** -- A platform fee calculated as a percentage (default 2%) of the order total, split between the restaurant and customer. Stored on the order as `arrive_fee_cents`.

**Arrival Status** -- A field on the order that tracks the customer's physical proximity to the restaurant. Possible values are `5_MIN_OUT`, `PARKING`, `AT_DOOR`, `EXIT_VICINITY`, and `null` (no arrival data yet).

**AT_DOOR** -- An arrival event indicating the customer has arrived at the restaurant entrance. If the order has not yet been dispatched, this event forces dispatch regardless of the configured trigger.

**CANCELED** -- A terminal order status. The customer canceled the order before it was dispatched to the restaurant. Only orders in PENDING_NOT_SENT or WAITING_FOR_CAPACITY can be canceled.

**Capacity** -- The system that limits concurrent active orders per restaurant per time window. Capacity is tracked in the CapacityTable using DynamoDB atomic counters.

**Capacity Window** -- A fixed time interval (default 300 seconds / 5 minutes) during which a limited number of orders can be active at a restaurant. Windows are calculated by flooring the current epoch timestamp to the nearest boundary.

**CloudFront** -- The AWS CDN used to host the customer-web and admin-portal frontend applications. CloudFront serves static assets from S3 and routes all SPA paths to index.html.

**COMPLETED** -- The terminal success status for an order. The customer has received their food and the order is closed. In SOFT receipt mode, this can happen automatically on EXIT_VICINITY.

**Correlation ID** -- A unique identifier for each API request, extracted from the API Gateway's `requestContext.requestId`. Used for distributed tracing across log entries.

**CORS** -- Cross-Origin Resource Sharing. The platform dynamically matches the request's Origin header against a whitelist of allowed origins and returns the appropriate headers. Managed centrally in `services/shared/python/shared/cors.py`.

**Customer** -- The default user role for people ordering food. Customers can browse restaurants, place orders, track their approach, and manage favorites. The role is stored as `custom:role = customer` in the Cognito JWT.

**Cutover** -- The transition from shadow mode to live mode for geofence-based dispatching. Controlled by the `LocationGeofenceCutoverEnabled` parameter. When enabled, geofence ENTER events trigger real order status transitions.

**Dispatch** -- The act of sending an order to the restaurant for preparation. Dispatch happens when the customer enters the vicinity and capacity is available. The order transitions from PENDING_NOT_SENT to SENT_TO_DESTINATION.

**Dispatch Trigger Event** -- The arrival event that initiates dispatch. Configurable per restaurant: `5_MIN_OUT` (default), `PARKING`, or `AT_DOOR`. Stored in the RestaurantConfigTable.

**DynamoDB** -- The NoSQL database service used for all persistent data storage. All tables use on-demand capacity mode.

**EventBridge** -- The AWS event bus that delivers Amazon Location Service geofence events to the GeofenceEventsFunction Lambda.

**EXPIRED** -- A terminal order status. The order's TTL elapsed before it was dispatched. A scheduled Lambda runs every 5 minutes to expire stale PENDING and WAITING orders.

**EXIT_VICINITY** -- An arrival event indicating the customer has left the restaurant area. If the order is in FULFILLING status with SOFT receipt mode, this triggers auto-completion.

**FULFILLING** -- An active order status indicating the customer has arrived and is being served. This is the last status before COMPLETED.

**Geofence** -- A virtual geographic boundary defined in Amazon Location Service. Each restaurant has three concentric geofence zones (vicinity, nearby, arrive) that map to arrival events.

**GeofenceEventsFunction** -- The Lambda function triggered by EventBridge when a device enters a geofence. It deduplicates events, finds the customer's active order, and either records a shadow event or triggers dispatch.

**GSI** -- Global Secondary Index. A DynamoDB feature that enables efficient queries on attributes other than the table's primary key. The OrdersTable has four GSIs; the RestaurantsTable has three.

**HARD** -- A receipt mode requiring explicit manual completion by the restaurant. Orders in HARD mode are not auto-completed when the customer exits the vicinity. See also SOFT.

**HTTP API** -- The type of API Gateway used by Arrive. HTTP APIs (v2) are lighter and cheaper than REST APIs (v1) and support JWT authorizers natively.

**Idempotency Key** -- A client-generated UUID sent in the `Idempotency-Key` request header to prevent duplicate order creation. Stored in the IdempotencyTable with a TTL.

**IN_PROGRESS** -- An active order status indicating the restaurant has begun preparing the order. Set by the restaurant via the status update endpoint.

**InMemoryTable** -- A Python class used in tests to mock DynamoDB table operations. Stores items in a dictionary and implements get_item, put_item, update_item, query, and scan.

**Lambda Layer** -- The shared code library (`services/shared/python/shared/`) that is mounted into every Lambda function at runtime. Contains auth, cors, logger, and serialization modules.

**Location Bridge** -- The module in the orders service (`location_bridge.py`) that publishes device GPS positions to the Amazon Location Service tracker.

**LocationGeofenceCollection** -- The Amazon Location Service resource that stores geofence zones for all restaurants.

**LocationTracker** -- The Amazon Location Service resource that receives and evaluates device GPS positions against geofences. Uses AccuracyBased filtering.

**make_response** -- A helper function in `shared/serialization.py` that constructs a Lambda response with the correct status code, CORS headers, and JSON body.

**MAX_ITEM_QTY** -- The maximum quantity allowed for a single item in an order. Currently set to 99.

**menu:read** -- A POS API key permission that allows reading the restaurant's menu.

**menu:write** -- A POS API key permission that allows syncing menus from the POS system.

**orders:read** -- A POS API key permission that allows listing and viewing orders.

**orders:write** -- A POS API key permission that allows creating orders, updating status, force-firing, and processing webhooks.

**PARKING** -- An arrival event indicating the customer is parking near the restaurant. Triggers dispatch if the order has not yet been sent.

**PAY_AT_RESTAURANT** -- The current payment mode. All orders are settled at the restaurant, not through the Arrive platform.

**PENDING_NOT_SENT** -- The initial order status after creation. The order exists but has not been dispatched to the restaurant. The restaurant does not see it yet.

**PITR** -- Point-in-Time Recovery. A DynamoDB feature that enables continuous backups and restoration to any second within the past 35 days. Enabled on all tables.

**POS** -- Point of Sale. An external system used by restaurants to manage transactions. The POS Integration service bridges these systems with Arrive.

**READY** -- An active order status indicating the food is prepared and waiting for the customer. Set by the restaurant via the status update endpoint.

**Receipt Mode** -- Controls how an order reaches COMPLETED. SOFT allows auto-completion; HARD requires manual completion. See SOFT and HARD.

**Restaurant Admin** -- A user role for restaurant staff. Restaurant admins can manage their own restaurant's orders, menu, configuration, and images, but cannot access other restaurants' data. The role is stored as `custom:role = restaurant_admin` with `custom:restaurant_id` identifying their restaurant.

**SAM** -- AWS Serverless Application Model. An extension of CloudFormation used to define and deploy the Arrive infrastructure. The root template is at `infrastructure/template.yaml`.

**SENT_TO_DESTINATION** -- An active order status indicating the order has been dispatched to the restaurant. This is the first status visible to the restaurant on their dashboard.

**Shadow Mode** -- The default operational mode for geofence events. In shadow mode, geofence ENTER events are recorded as metadata on orders but do not trigger status transitions. This allows validation of geofence accuracy before enabling live dispatch.

**SOFT** -- The default receipt mode. Orders in SOFT mode auto-complete when the customer exits the vicinity (EXIT_VICINITY event) while the order is in FULFILLING status. See also HARD.

**StructuredLogger** -- The logging adapter defined in `shared/logger.py` that produces single-line JSON log entries for CloudWatch Insights. Supports bound context fields and hierarchical logger names.

**TTL** -- Time to Live. A DynamoDB feature that automatically deletes items after a specified timestamp. Used on CapacityTable, IdempotencyTable, GeofenceEventsTable, PosApiKeysTable, PosWebhookLogsTable, and OrdersTable.

**UpdatePlan** -- A dataclass returned by the dispatch engine's decision functions. Contains the fields to set, fields to remove, conditional status checks, and the response body. Separates decision logic from I/O.

**Vicinity** -- The geographic zone around a restaurant that triggers order dispatch. When a customer enters the vicinity (as reported by the mobile app or detected by geofence), their order can be sent to the restaurant.

**WAITING_FOR_CAPACITY** -- An intermediate order status. The customer has entered the vicinity, but the restaurant's current capacity window is full. The order queues until capacity opens up.

**Window Start** -- The epoch-second timestamp representing the beginning of a capacity window. Calculated by flooring the current time to the nearest window boundary. For a 300-second window, timestamp 1700000150 yields window start 1700000000.

**Work Units** -- A numeric measure of an item's preparation complexity. Each menu item has a `work_units` value (formerly `prep_units`) that contributes to the order's total workload estimation.

**X-POS-API-Key** -- The HTTP header used by POS systems to authenticate with the POS Integration service. Contains the raw API key, which is SHA-256 hashed for lookup.

---

## Environment Variables

The following environment variables are referenced across the platform:

**CAPACITY_TABLE** -- DynamoDB table name for capacity tracking.

**CORS_ALLOW_ORIGIN** -- Allowed CORS origin for the customer web application. Set to the CloudFront URL in production.

**CORS_ALLOW_ORIGIN_ADMIN** -- Allowed CORS origin for the admin portal. Set to the admin CloudFront URL in production.

**GEOFENCE_EVENTS_TABLE** -- DynamoDB table name for geofence event deduplication.

**IDEMPOTENCY_TABLE** -- DynamoDB table name for order creation idempotency.

**LOCATION_GEOFENCE_COLLECTION_NAME** -- Name of the Amazon Location Service geofence collection.

**LOCATION_GEOFENCE_CUTOVER_ENABLED** -- Boolean flag controlling whether geofence events trigger real status transitions.

**LOCATION_GEOFENCE_FORCE_SHADOW** -- Emergency rollback flag that forces shadow mode even when cutover is enabled.

**LOCATION_TRACKER_NAME** -- Name of the Amazon Location Service tracker for device position updates.

**LOG_LEVEL** -- Logging level (default: INFO). Accepts standard Python logging levels.

**ORDERS_TABLE** -- DynamoDB table name for orders.

**POS_API_KEYS_TABLE** -- DynamoDB table name for POS API key records.

**RESTAURANT_CONFIG_TABLE** -- DynamoDB table name for per-restaurant operational configuration.

**SERVICE_NAME** -- Identifier for the service, included in every log entry (default: arrive).
