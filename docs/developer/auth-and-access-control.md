# Authentication and Access Control

The Arrive platform uses two distinct authentication models. Web and mobile clients authenticate with Cognito JWT tokens, which carry user identity and role information. External POS systems authenticate with API keys that are scoped to a specific restaurant and carry a permissions set. This document explains both models in detail, including how claims flow through the system, how role-based access is enforced, and how the CORS policy protects cross-origin requests.

## Cognito JWT Authentication

All customer-facing, restaurant-admin, and admin routes use Amazon Cognito for authentication. The Cognito User Pool is configured with email-based sign-up, Google federated identity, and custom attributes for role and restaurant assignment.

### Token Issuance

When a user signs in (either with email/password or via Google federation), Cognito issues a JWT access token. This token contains standard claims (`sub`, `email`, `cognito:username`) and custom claims that the platform uses for authorization:

- `custom:role` -- one of `customer`, `restaurant_admin`, or `admin`
- `custom:restaurant_id` -- for `restaurant_admin` users, the ID of their assigned restaurant

These custom attributes are set during user provisioning (either by the PostConfirmation Lambda trigger for self-registered users, or by an admin when creating restaurant staff accounts).

### Token Validation at the Gateway

API Gateway validates the JWT before the Lambda handler executes. The HTTP API is configured with a `CognitoJWT` authorizer that checks:

1. The token's `iss` claim matches the Cognito User Pool endpoint.
2. The token's `aud` claim matches the User Pool Client ID.
3. The token has not expired.
4. The token's signature is valid.

If any check fails, API Gateway returns a 401 response and the Lambda function is never invoked. This means all Lambda handlers can assume the caller has been authenticated at the infrastructure level.

### Claim Extraction in Lambda

Once the request reaches the Lambda handler, the JWT claims are available in the event at `requestContext.authorizer.jwt.claims` (for HTTP API v2 format). The shared layer's `auth.py` module normalizes these claims into a consistent dictionary.

The `get_user_claims(event)` function extracts:

```python
{
    'role': 'customer',                 # from custom:role
    'restaurant_id': None,              # from custom:restaurant_id
    'customer_id': 'sub_abc123',        # from sub
    'user_id': 'sub_abc123',            # alias for customer_id
    'username': 'jane@example.com',     # from cognito:username
    'email': 'jane@example.com',        # from email
}
```

The function handles both HTTP API v2 (`requestContext.authorizer.jwt.claims`) and REST API v1 (`requestContext.authorizer.claims`) event formats. If no claims are found (e.g., the authorizer is not configured for this route), it returns an empty dictionary.

A fallback rule handles legacy and federated users who may not have the `custom:role` attribute: if a user has a `sub` claim but no `role` and no `restaurant_id`, they are treated as a `customer`. This ensures that users who signed up before custom attributes were introduced, or who signed in through Google federation, are not locked out.

### Role-Based Routing

Each service's router (`app.py`) enforces role-based access after extracting claims. The pattern is consistent across services:

**Customer Routes** require the `customer` role. The router verifies that the caller has a `customer_id` (the `sub` claim) and that their role is either explicitly `customer` or is absent with no `restaurant_id` (the legacy fallback). This is the most permissive check, since most users are customers.

**Restaurant Routes** require either `restaurant_admin` or `admin` role. For `restaurant_admin` users, an additional check verifies that the `restaurant_id` in the URL path matches the `restaurant_id` in their JWT claims. A restaurant admin can only access their own restaurant's data. Platform admins can access any restaurant.

**Admin Routes** require the `admin` role exclusively. These include operations like creating restaurants, managing global configuration, and deleting restaurants.

Here is the authorization flow in the Orders service router as an example:

```python
claims = db.get_auth_claims(event)
role = db.get_user_role(event)

# Customer routes: must be authenticated, must be a customer
if route_key in CUSTOMER_ROUTES:
    if not customer_id:
        return make_response(401, {'error': 'Unauthorized'})
    is_customer = role == 'customer' or (not role and not assigned_restaurant_id)
    if not is_customer:
        return make_response(403, {'error': 'Access denied'})

# Restaurant routes: must be admin or restaurant_admin for this restaurant
if route_key in RESTAURANT_ROUTES:
    if role not in ('admin', 'restaurant_admin'):
        return make_response(403, {'error': 'Access denied'})
    if role == 'restaurant_admin':
        if requested_restaurant_id != assigned_restaurant_id:
            return make_response(403, {'error': 'Access denied'})
```

Authorization decisions are made in the router, not in individual handler functions. By the time a handler is called, the caller's identity and permissions have already been verified. Handlers can safely assume they are dealing with an authorized request.

### The Inactive Restaurant Gate

The Restaurants service adds an additional authorization layer for restaurant_admin users: the inactive restaurant gate. When a restaurant_admin makes any request, the router first checks whether their assigned restaurant is active:

```python
if role == 'restaurant_admin' and restaurant_id:
    restaurant = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
    if restaurant and not restaurant.get('active', False):
        # Only allow reading and updating own restaurant profile
        allow_request = route_key in (
            'GET /v1/restaurants',
            'GET /v1/restaurants/{restaurant_id}',
            'PUT /v1/restaurants/{restaurant_id}',
        )
        if not allow_request:
            return make_response(403, {
                'error': 'Restaurant is currently inactive/on-hold. '
                         'Please contact support.'
            })
```

If the restaurant is inactive (deactivated by an admin), the restaurant_admin can still view and update their own restaurant profile (to correct information, update images, etc.), but they cannot manage menus, configuration, orders, or any other operational resource. Crucially, the `update_restaurant` handler strips the `active` field from the request body for restaurant_admin callers, preventing self-reactivation.

This gate protects against a scenario where a restaurant is deactivated for policy violations but the restaurant_admin still has valid Cognito credentials.

## POS API Key Authentication

The POS Integration service uses a completely separate authentication model. POS systems send an API key in the `X-POS-API-Key` HTTP header. There is no JWT, no Cognito involvement, and no user identity -- only a key that maps to a restaurant and a set of permissions.

### Key Lifecycle

API keys are provisioned through an administrative process (not currently exposed as an API endpoint). When a new key is created:

1. A random API key string is generated.
2. The SHA-256 hash of the key is computed: `hashlib.sha256(raw_key.encode()).hexdigest()`.
3. A record is stored in the `PosApiKeysTable` with the hash as the partition key, along with the `restaurant_id`, `permissions` array, `pos_system` identifier, and optionally a `ttl` for key expiration.
4. The raw key is returned to the administrator and never stored.

This design ensures that even if the DynamoDB table is compromised, the raw API keys are not exposed. An attacker would need to reverse a SHA-256 hash to recover the key, which is computationally infeasible.

### Key Validation

On every request to the POS HTTP API, the `authenticate_request` function:

1. Extracts the raw key from the `X-POS-API-Key` header (case-insensitive header lookup).
2. Computes the SHA-256 hash of the raw key.
3. Performs a DynamoDB `get_item` using the hash as the partition key.
4. If no item is found, authentication fails (returns `None`).
5. If an item is found, checks the `ttl` attribute against the current time. If the key has expired, authentication fails.
6. If the key is valid, returns the key record containing `restaurant_id`, `pos_system`, and `permissions`.

If authentication fails, the router returns a 401 response with a message indicating the key is missing or invalid.

### Permission Model

Each API key carries a permissions array that controls which operations it can perform. Permissions follow a `resource:action` format:

- `orders:read` -- can list and view orders
- `orders:write` -- can create orders, update status, force-fire, and process webhooks
- `menu:read` -- can read the restaurant's menu
- `menu:write` -- can sync menus from the POS system

A wildcard permission (`*`) grants all permissions. If the permissions array is empty or missing, the key has no permissions (fail-closed).

The router checks permissions before dispatching to handlers:

```python
key_record = authenticate_request(event)
if not key_record:
    return 401

if route_key == 'POST /v1/pos/orders':
    if not require_permission(key_record, 'orders:write'):
        return 403
    return handle_create_order(body, key_record)
```

The `require_permission` function checks whether the requested permission is in the key's permissions array or whether the key has the wildcard permission.

### Separation from Cognito

The POS service runs on a separate HTTP API Gateway that does not have the Cognito JWT authorizer configured. This is a deliberate architectural choice: POS systems are machine-to-machine integrations that have no concept of Cognito user pools or JWTs. Mixing the two authentication models on the same gateway would create confusion about which mechanism applies to which route.

The POS HTTP API Gateway is conditionally deployed via the `DeployPosIntegration` SAM parameter. When set to `false` (the default), the entire POS stack -- API Gateway, Lambda function, and associated resources -- is not created.

## CORS Policy

Cross-Origin Resource Sharing (CORS) headers are included in every Lambda response. The CORS implementation is centralized in `services/shared/python/shared/cors.py`.

### Dynamic Origin Matching

The `cors_headers(event)` function reads the request's `Origin` header and matches it against a whitelist of allowed origins. The whitelist is constructed from:

1. The `CORS_ALLOW_ORIGIN` environment variable (set to the customer web app's CloudFront URL in production).
2. The `CORS_ALLOW_ORIGIN_ADMIN` environment variable (set to the admin portal's CloudFront URL).
3. `http://localhost:5173` (customer web dev server).
4. `http://localhost:5174` (admin portal dev server).

If the request's origin matches any entry in the whitelist, that origin is returned in `Access-Control-Allow-Origin`. If no match is found, the first configured origin is used as a fallback. This dynamic matching ensures that both the customer and admin applications receive correct CORS headers without using `*`.

### Headers

Every response includes:

```
Content-Type: application/json
Access-Control-Allow-Origin: <matched origin>
Access-Control-Allow-Headers: Authorization,Content-Type,Idempotency-Key
Vary: Origin
```

The `Vary: Origin` header ensures that caching proxies (like CloudFront) do not serve a response with one origin's CORS headers to a request from a different origin.

### Health and Error Responses

Health check endpoints, 404 responses, and 500 error responses all include CORS headers. This prevents browsers from masking the actual error with a CORS error, which would make debugging difficult. The `make_response` helper in the shared serialization module ensures that every response path includes CORS headers by accepting the event as an optional parameter for origin matching.

## Security Principles

Several security principles are applied consistently across both authentication models:

**Fail closed.** If claims are missing, the request is denied. If the role is unrecognized, access is denied. If a POS key has no permissions, all operations are forbidden. The system defaults to denial and requires explicit evidence of authorization.

**Defense in depth.** JWT validation happens at two levels: API Gateway rejects invalid tokens before Lambda runs, and the Lambda router checks roles and restaurant ownership. Even if one layer fails, the other catches unauthorized access.

**Least privilege.** POS API keys carry only the permissions they need. A key intended for menu synchronization only gets `menu:read` and `menu:write`, not `orders:write`. Restaurant admins can only access their own restaurant's data.

**No secrets in storage.** POS API keys are stored as SHA-256 hashes. Cognito handles password storage. The platform never stores raw secrets in DynamoDB or application code.

**Short-lived credentials.** JWT tokens have Cognito-managed expiration. POS API keys support TTL-based expiration via DynamoDB. Neither credential type is permanent by default.
