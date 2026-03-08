# Shared Lambda Layer

The shared Lambda layer provides four foundational modules that every backend service depends on: CORS handling, authentication, structured logging, and JSON serialization. These modules live in `services/shared/python/shared/` and are deployed as an AWS Lambda Layer, making them available to all service Lambdas without code duplication.


## Why a Shared Layer

The alternative to a shared layer is copying these utilities into each service's source directory. This was the original approach, and it created exactly the problems you would expect: a CORS fix in one service would not propagate to others, authentication logic would diverge, and log formats would be inconsistent across services, making CloudWatch Insights queries unreliable.

A Lambda Layer solves these problems at the infrastructure level. All services reference the same layer version, and updating the layer atomically updates all services on their next deployment. The layer adds roughly 50 KB to each Lambda's deployment package, which is negligible compared to the boto3 runtime.

The four modules were chosen for the layer because they meet two criteria: they are needed by every service, and their behavior must be consistent across the platform. Service-specific utilities (like the orders engine or the POS mapper) remain in their respective service directories.


## CORS Module

**File**: `services/shared/python/shared/cors.py`

The CORS module solves a specific problem: the Arrive platform has two frontend applications (customer web and admin portal) running on different origins, and API Gateway's built-in CORS configuration cannot dynamically select between them.

### Dynamic Origin Matching

The `get_cors_origin(event)` function reads the `Origin` header from the incoming request and checks it against a list of allowed origins. This list is constructed at module load time from two environment variables (`CORS_ALLOW_ORIGIN` for the customer app, `CORS_ALLOW_ORIGIN_ADMIN` for the admin portal) plus two localhost fallbacks for local development (`http://localhost:5173` and `http://localhost:5174`).

If the request's origin matches one of the allowed origins, that exact origin is returned. If it does not match (or if there is no Origin header), the first configured origin is returned as a fallback. The module never returns a wildcard `*` unless no origins are configured at all, which should only happen in a misconfigured deployment.

This approach is necessary because the `Access-Control-Allow-Origin` header does not support multiple values. The browser expects exactly one origin or `*`, and responding with the wrong origin causes the browser to reject the response entirely. By echoing back the matched origin, the module works correctly for both frontends without using a wildcard.

### Response Headers

The `cors_headers(event)` function returns a complete headers dictionary:

- `Content-Type: application/json` -- All API responses are JSON.
- `Access-Control-Allow-Origin` -- The dynamically matched origin.
- `Access-Control-Allow-Headers: Authorization,Content-Type,Idempotency-Key` -- The three headers the frontends send.
- `Vary: Origin` -- Tells CDNs and proxies that the response varies by the Origin header, preventing incorrect caching of CORS headers.

### Static Fallback

The `CORS_HEADERS` module-level constant is a static dict initialized with the first configured origin. This exists for code paths that do not have access to the request event (e.g., error responses generated before the event is parsed). The static fallback is always the customer app origin (since it is listed first), which is correct for the majority of traffic.


## Auth Module

**File**: `services/shared/python/shared/auth.py`

The auth module extracts and normalizes Cognito JWT claims from API Gateway events. It does not validate the JWT itself -- API Gateway's JWT authorizer handles that. The module's job is to translate the raw claims into a consistent dict that handler code can rely on.

### Dual Event Format Support

API Gateway emits two different event formats depending on the API type:

- **HTTP API v2**: Claims are at `event.requestContext.authorizer.jwt.claims`
- **REST API v1**: Claims are at `event.requestContext.authorizer.claims`

The `get_raw_claims(event)` function tries the v2 path first, then falls back to v1. If neither exists, it returns an empty dict. This dual-path support exists because the platform uses HTTP APIs for most services but may use REST APIs for specific endpoints that need features like request validation or API keys.

### Claim Normalization

The `get_user_claims(event)` function normalizes raw claims into a stable dict with six fields:

- `role`: From `custom:role` or `role`. Falls back to `'customer'` if the user has a `sub` but no role and no restaurant_id.
- `restaurant_id`: From `custom:restaurant_id` or `restaurant_id`.
- `customer_id`: The `sub` claim.
- `user_id`: Alias for `customer_id` (backward compatibility).
- `username`: From `cognito:username` or `username`.
- `email`: The `email` claim.

### Role Fallback Logic

The role fallback deserves explanation. When a user signs up through social federation (Google, Apple), Cognito may not set the `custom:role` attribute. These users should be treated as customers. However, the module cannot blindly default to `'customer'` because a restaurant admin whose role claim was not properly set should not be granted customer access to place orders.

The compromise is conservative: the default `'customer'` role is only applied when the user has a `sub` claim (proving they are authenticated) AND does not have a `restaurant_id` (proving they are not bound to a restaurant). If a user has a restaurant_id but no role, the role field remains empty, which causes all role checks to fail -- a fail-closed default.

### Fail-Closed Defaults

The `get_user_role(event)` convenience function defaults to an empty string, not `'customer'`. This is intentional: an empty string will not match any role check (`role == 'admin'`, `role == 'customer'`, etc.), so a missing role effectively denies access everywhere. The caller must explicitly handle the empty-role case if they want to allow it.

Similarly, `get_customer_id(event)` and `get_restaurant_id(event)` return `None` when the claim is absent, forcing callers to check for None before using the value.


## Logger Module

**File**: `services/shared/python/shared/logger.py`

The logger module provides structured JSON logging optimized for CloudWatch Insights. Every log line is a single JSON object, enabling queries like:

```
fields @timestamp, level, correlation_id, order_id, message
| filter level = "ERROR"
| sort @timestamp desc
```

### JSON Formatter

The `JSONFormatter` class extends Python's `logging.Formatter` to serialize log records as JSON. The output includes standard fields (`timestamp`, `level`, `logger`, `message`, `service`) plus all custom fields passed via the `extra` parameter. Standard LogRecord fields (like `pathname`, `lineno`, `funcName`) are excluded to keep log lines concise.

Exception information is included as a formatted traceback string in the `exception` field when `exc_info=True` is passed to the log call.

### Structured Logger

The `StructuredLogger` class is a `logging.LoggerAdapter` that supports bound context. The `bind()` method returns a new logger instance with additional context fields that are automatically included in every subsequent log call. This is used extensively in handlers:

```python
req_log = log.bind(correlation_id=correlation_id, handler="router")
req_log = req_log.bind(order_id=order_id, customer_id=customer_id)
req_log.info("order_created")  # Includes all bound fields
```

Binding creates a new logger rather than mutating the existing one, which is safe for concurrent use and prevents context leakage between requests.

### Correlation ID Extraction

The `extract_correlation_id(event)` function extracts a request ID from the API Gateway event, trying `requestContext.requestId` first and falling back to the `x-amzn-requestid` header. This ID links all log lines from a single request, even across log groups.

### Timer

The `Timer` context manager measures elapsed time in milliseconds:

```python
with Timer() as t:
    db.orders_table.get_item(Key={'order_id': order_id})
req_log.info("order_fetched", extra={"duration_ms": t.elapsed_ms})
```

Timer uses `time.perf_counter()` for high-resolution measurement. The elapsed time is rounded to one decimal place.

### Root Logger Configuration

The `_configure_root()` function runs once per Lambda cold start. It removes all existing
handlers from the root logger and installs the JSON formatter. This is necessary because
Lambda's default handler produces plain-text output, and CloudWatch Insights cannot parse
mixed formats reliably. Without this override, some log lines would be JSON and others
would be plain text, making automated analysis impossible.

The function uses a module-level `_configured` flag to ensure it runs only once, even if
`get_logger()` is called from multiple modules during import.

The log level is configurable via the `LOG_LEVEL` environment variable (default: INFO).
The service name is configurable via `SERVICE_NAME` (default: "arrive") and is included
in every log entry for filtering by service in a shared log group.

### Practical Usage Patterns

Services typically create a module-level logger and then create request-scoped loggers
by binding context:

```python
# Module level (created once at import time)
log = get_logger("orders.customer", service="orders")

# Request level (created per invocation, includes request-specific context)
req_log = log.bind(correlation_id=correlation_id, handler="create_order")

# After parsing input (adds more context without losing previous bindings)
req_log = req_log.bind(order_id=order_id, customer_id=customer_id)
```

This progressive binding pattern means early log lines have less context (just the
correlation ID) while later log lines include all relevant identifiers. Every log line
from a single request shares the same correlation_id, enabling reconstruction of the
full request timeline in CloudWatch Insights.


## Serialization Module

**File**: `services/shared/python/shared/serialization.py`

The serialization module solves the DynamoDB Decimal problem and provides a standard response builder.

### Decimal Handling

DynamoDB returns all numbers as Python `Decimal` objects. Python's `json.dumps` does not know how to serialize `Decimal`, so every JSON serialization call needs a custom default function. The `decimal_default(obj)` function converts `Decimal` to `float`, which is sufficient for the platform's use cases (prices, timestamps, counts).

This function is used as `json.dumps(body, default=decimal_default)` throughout the codebase. Without it, every handler would need its own Decimal conversion, or would need to manually convert Decimals to floats before serialization.

### Response Builder

The `make_response(status_code, body, event)` function constructs a Lambda proxy response with three components: the status code, CORS headers (using the dynamic `cors_headers(event)` function), and the JSON-serialized body. The `event` parameter is optional -- when provided, it enables dynamic CORS origin matching; when omitted, the static fallback is used.

This function eliminates the most common source of response-building bugs: forgetting
to include CORS headers. Before this function existed, handlers that returned error
responses often omitted CORS headers, causing browsers to show opaque network errors
instead of the actual error message. The browser would reject the response at the CORS
preflight level, and the developer tools would show "CORS error" with no visibility
into the actual 400 or 500 response body.

### Integration Pattern

Each service's `utils.py` or `db.py` re-exports `make_response` from the shared layer:

```python
# services/restaurants/src/utils.py
from shared.serialization import make_response  # noqa: F401 -- re-exported

# services/orders/src/db.py
from shared.serialization import decimal_default  # noqa: F401 -- re-exported
```

This re-export pattern allows handler modules to import everything they need from a
single service-local module (`from utils import make_response`) rather than reaching
into the shared layer directly. This makes the shared layer an implementation detail
that handlers do not need to know about, and it makes test mocking simpler because
there is only one import path to patch.


## Design Principles

The shared layer follows several design principles that explain its current structure:

1. **No service-specific logic**: The layer contains only utilities that are genuinely
   universal. Anything specific to orders, restaurants, or POS belongs in the service.

2. **Defensive defaults**: Functions default to safe values. Missing CORS origins
   produce the first configured origin (not wildcard). Missing roles produce empty
   strings (not "customer"). Missing claims produce empty dicts (not None).

3. **No external dependencies**: The layer uses only the Python standard library and
   boto3 (which is provided by the Lambda runtime). This keeps the layer lightweight
   and avoids version conflicts with service-level dependencies.

4. **Backward compatibility**: New fields can be added to `get_user_claims()` without
   breaking existing callers. The `CORS_HEADERS` static dict is maintained alongside
   the dynamic `cors_headers()` function for code that cannot access the event.
