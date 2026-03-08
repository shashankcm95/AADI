# Security Guide

This document describes the security architecture of the Arrive platform. It covers the dual authentication model, role-based authorization, POS API key lifecycle, CORS policy, S3 access controls, IAM least-privilege design, input validation, the comprehensive security review process, and known residual risks.

---

## Authentication Model

Arrive uses two distinct authentication mechanisms depending on who is making the request.

### Cognito JWT Authentication

All customer-facing and admin-facing API endpoints are protected by Amazon Cognito JWT authentication. When a user signs in through the Cognito Hosted UI or via the Amplify client library, they receive an ID token containing their identity claims. This token is sent as a Bearer token in the `Authorization` header of every API request.

Each API Gateway HTTP API (Orders, Restaurants, Users) is configured with a Cognito JWT authorizer as its default authorizer. API Gateway validates the token's signature, expiration, issuer, and audience before the request reaches the Lambda function. If the token is invalid or missing, API Gateway returns a 401 response without invoking the Lambda.

The JWT authorizer configuration is identical across all three service APIs: the issuer is the Cognito User Pool's OIDC endpoint (`https://cognito-idp.{region}.amazonaws.com/{pool-id}`), and the audience is the User Pool Client ID.

### POS API Key Authentication

The POS Integration service uses a completely separate authentication mechanism. POS systems (such as Toast, Square, or Clover) authenticate by sending a plaintext API key in the `X-POS-API-Key` HTTP header. The POS HTTP API does not have a Cognito authorizer; it is an open API Gateway endpoint. Authentication is enforced at the application level by the POS Lambda function.

When a request arrives, the `authenticate_request` function in `services/pos-integration/src/auth.py` extracts the API key from the header, computes its SHA-256 hash, and performs a DynamoDB GetItem lookup against the `PosApiKeysTable`. If the key is found, not expired, and has the required permissions, the request proceeds. If any check fails, the function returns a 401 or 403 response.

This separation exists because POS systems are server-to-server integrations that cannot participate in OAuth flows. API key authentication is simpler and more appropriate for this use case.

---

## Authorization: Role-Based Access Control

After authentication, authorization is enforced at the application level based on the user's role. Cognito stores the role in a custom attribute named `custom:role`. The shared authentication utility `services/shared/python/shared/auth.py` provides functions to extract and normalize these claims.

### Roles

The platform defines three roles:

**customer** is the default role assigned to every new user by the PostConfirmation Lambda trigger. Customers can create orders, view their own orders, update their own profile, manage their favorites, and report their location for arrival tracking.

**restaurant_admin** is assigned when a platform admin invites a user to manage a specific restaurant. This role grants access to the restaurant's orders, menu, configuration, and images. A restaurant_admin's Cognito profile also carries a `custom:restaurant_id` attribute that binds them to exactly one restaurant. The authorization logic verifies that a restaurant_admin can only access resources belonging to their assigned restaurant.

**admin** is the platform superuser role. Admins can create and manage restaurants, invite restaurant admins, view all orders across all restaurants, and modify global configuration.

### Authorization Flow

Each Lambda handler extracts user claims using `get_user_claims(event)`, which returns a normalized dictionary containing `role`, `restaurant_id`, `customer_id`, `user_id`, `username`, and `email`. The handler then checks the role against the required role for the operation.

Authorization is fail-closed: if the role claim is missing, empty, or unrecognized, the request is denied. Legacy or federated users who lack the `custom:role` attribute are automatically assigned the `customer` role if they have a `sub` claim and no `restaurant_id`, ensuring backward compatibility without granting elevated privileges.

Restaurant admin operations additionally verify that the `restaurant_id` in the user's claims matches the `restaurant_id` in the request path. This prevents a restaurant admin from accessing another restaurant's data even if they craft a request with a different restaurant ID.

---

## POS API Key Lifecycle

POS API keys follow a secure lifecycle from provisioning through expiry.

### Key Provisioning

When a new POS integration is set up for a restaurant, an administrator generates a random API key (a high-entropy string). Before storing it, the system computes `hashlib.sha256(raw_key.encode('utf-8')).hexdigest()` and writes only this hash to the `PosApiKeysTable` as the `api_key` partition key. The raw plaintext key is returned to the administrator exactly once and is never stored in any system.

Each key record in DynamoDB contains: the SHA-256 hash (as the partition key), the `restaurant_id` the key is authorized for, the `pos_system` identifier (e.g., `toast`, `square`, `clover`, `generic`), a `permissions` list, an optional `ttl` for automatic expiry, and a `created_at` timestamp.

### Permission Model

Permissions follow a `resource:action` format. Common permissions include `orders:write` (create and update orders), `orders:read` (list orders), `menu:read` (read the menu), `menu:write` (sync the menu), and `webhook:write` (submit webhook events). A wildcard permission `*` grants access to all operations.

The `require_permission` function checks whether a key record contains the required permission for the requested operation. If the key lacks the permission, the request is denied with a 403 response. This is a fail-closed design: keys with an empty or missing permissions list cannot perform any operations.

### TTL Expiry

Keys can be provisioned with a `ttl` attribute (Unix epoch seconds). The `validate_key` function checks this TTL against the current time before returning the key record. Expired keys are rejected even if the DynamoDB item still exists (DynamoDB TTL cleanup is eventually consistent and may take up to 48 hours). This application-level check ensures immediate expiry enforcement.

### Key Rotation

To rotate a key, provision a new key for the same restaurant and permissions, distribute it to the POS vendor, and then either remove the old key's DynamoDB item or let its TTL expire. Both keys can coexist during the transition period since each has a unique hash.

---

## CORS Policy

Arrive's CORS implementation uses a dynamic origin resolution strategy defined in `services/shared/python/shared/cors.py`.

### Dual-Origin Support

Each Lambda function receives two CORS origin environment variables: `CORS_ALLOW_ORIGIN` (the customer-web CloudFront domain) and `CORS_ALLOW_ORIGIN_ADMIN` (the admin-portal CloudFront domain). Additionally, `http://localhost:5173` and `http://localhost:5174` are hardcoded as development fallback origins.

When a request arrives, the `cors_headers(event)` function reads the `Origin` header from the request. If this origin matches any entry in the allowed origins list, that origin is returned as the `Access-Control-Allow-Origin` header. If the origin does not match (or is missing), the function falls back to the first configured origin. This ensures that browsers making requests from either the customer app or the admin portal receive the correct CORS headers.

### Headers and Methods

The CORS headers include `Content-Type`, `Authorization`, and `Idempotency-Key` in `Access-Control-Allow-Headers`. The `Vary: Origin` header is always set, which is critical for CDN and browser cache correctness when multiple origins are served by the same endpoint.

At the API Gateway level, CORS preflight (OPTIONS) handling is configured in each HTTP API's `CorsConfiguration` block. This handles the browser's preflight request before it reaches the Lambda function. The Lambda-level CORS headers handle the actual response headers on non-preflight requests.

---

## S3 Security

All S3 buckets in the stack have comprehensive public access blocking enabled. The `PublicAccessBlockConfiguration` on every bucket sets `BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, and `RestrictPublicBuckets` to `true`. This four-layer block prevents any accidental public access through ACLs, bucket policies, or access points.

### Frontend Hosting Buckets

The CustomerWebBucket and AdminPortalBucket are accessible only through CloudFront Origin Access Identities (OAIs). The bucket policies explicitly grant `s3:GetObject` only to the specific OAI principal. Direct S3 access via the bucket's website endpoint or S3 API is blocked.

### Media Buckets

The RestaurantImagesBucket and UserAvatarsBucket are never directly accessible to end users. Instead, Lambda functions generate presigned URLs for both uploads and downloads. Presigned GET URLs for user avatars have a TTL of 900 seconds (15 minutes). Presigned PUT URLs for restaurant images have a TTL of 3600 seconds (1 hour).

The avatar upload endpoint validates that the S3 key follows the pattern `avatars/{user_id}/...`, preventing users from writing to arbitrary keys in the bucket. Similarly, restaurant image uploads are scoped to the requesting restaurant's key prefix.

S3 CORS rules on the media buckets allow GET, PUT, and HEAD requests only from the configured CORS origins (the CloudFront domains), not from wildcards.

---

## IAM Least-Privilege Design

Every Lambda function's IAM execution role is scoped to the minimum permissions required for its operation. This was a focus of the 14-phase security review, which identified and resolved several IAM over-permission issues.

The PostConfirmation function has `cognito-idp:AdminUpdateUserAttributes` scoped to the specific User Pool ARN, not a wildcard. It has DynamoDB CRUD access only to the UsersTable.

The Orders function has no `dynamodb:Scan` permission on any table except through the specifically configured `ExpireOrdersFunction`, which needs Scan as a fallback mechanism. The geo:BatchUpdateDevicePosition permission is scoped to the specific Location Tracker ARN.

The Restaurants function has Cognito permissions for user management operations scoped to the specific User Pool ARN. Its geofence permissions (`geo:BatchPutGeofence`, `geo:BatchDeleteGeofence`) are scoped to the specific geofence collection ARN.

The POS Integration function has explicit item-level DynamoDB permissions (`GetItem`, `PutItem`, `UpdateItem`, `Query`) on cross-service tables. It does not have `Scan` permission, preventing it from performing full-table reads.

Where conditional resources are involved (such as the Location Tracker or Geofence Collection which may not be named), the templates use `!If` conditions to either reference the real resource ARN or a harmless placeholder ARN (`no-tracker-assigned`), avoiding IAM policy validation errors.

---

## Input Validation

Input validation is enforced at multiple levels throughout the stack.

**Email validation** uses a regex pattern to prevent Cognito filter injection attacks. When listing users by email (for admin operations), the email input is validated against a strict pattern before being used in a Cognito `ListUsers` filter expression.

**Field length limits** are enforced on user profile fields (name, phone number), restaurant fields (name, description, cuisine), and menu item fields (name, description, price). These limits prevent oversized payloads from consuming DynamoDB write capacity or causing display issues in the frontend.

**Decimal precision** for menu item prices uses Python's `Decimal` type with `ROUND_HALF_UP` quantization to two decimal places. This ensures financial calculations are exact and consistent, avoiding the floating-point precision issues that would arise from using Python floats.

**Order quantity limits** are enforced with a `MAX_ITEM_QTY` guard (set to 99) in the order engine. This prevents absurdly large orders from consuming all of a restaurant's capacity.

**Idempotency key validation** ensures that the `Idempotency-Key` header, when present on order creation requests, is used to prevent duplicate order processing. The key is stored in the IdempotencyTable with a TTL.

---

## The 14-Phase Security Review

The Arrive codebase underwent a systematic 14-phase code review that examined every file in the repository for bugs, security vulnerabilities, and operational risks. The review produced 70 backlog items (BL-001 through BL-070), all of which have been resolved.

The phases covered authentication and identity (Phase 1), the shared layer (Phase 2), the Orders service (Phase 3), the Restaurants service (Phase 4), the Users service (Phase 5), POS integration (Phase 6), infrastructure templates (Phase 7), the customer web frontend (Phase 8), the admin portal (Phase 9), the mobile iOS app (Phase 10), the test suite (Phase 11), scripts and tooling (Phase 12), open backlog audit (Phase 13), and final security and performance hardening (Phase 14).

Key security fixes from this review include: POS API keys changed from plaintext storage to SHA-256 hashing (BL-021); IAM wildcards on the PostConfirmation function, Orders geo tracker, and Restaurants geofence collection replaced with specific resource ARNs (BL-043, BL-044, BL-045); S3 CORS `AllowedOrigins` wildcards replaced with specific CloudFront domains (BL-046, BL-047); DynamoDB Scan permission removed from the POS function (BL-048); webhook routes restricted to require matching permissions (BL-039); and inactive restaurant admin access gates properly enforced (BL-002).

---

## Residual Risks

Despite the comprehensive review, some risks remain that operators should be aware of.

**Race conditions under extreme concurrency** are theoretically possible on order state transitions. DynamoDB conditional writes prevent most races, but under extreme concurrent load (many simultaneous state transition attempts for the same order), a small window exists where optimistic locking could produce a 500 error instead of a clean conflict response. The system handles this safely (no data corruption), but the error response is not ideal from a user experience perspective.

**Geofence signal loss** on mobile devices can cause missed arrival events. If a customer's device loses GPS signal or the app is killed by the OS before entering a geofence, the geofence ENTER event will not fire. The system mitigates this with manual vicinity reporting (the customer can tap a button in the app), but the automatic geofence path has an inherent dependency on device GPS availability.

**Cognito token revocation** is not instantaneous. If a user's role needs to be revoked immediately, the existing JWT tokens remain valid until they expire. Cognito access tokens have a default expiry of 1 hour. For immediate revocation, you would need to disable the user in Cognito and rely on the authorization layer to reject requests from disabled accounts.

**POS API key hashing is one-way.** If a POS vendor loses their API key, it cannot be recovered from the SHA-256 hash. A new key must be provisioned and the old one revoked. This is by design (storing reversible keys would be a security regression), but it means key recovery is impossible.

**CloudFront OAI is a legacy pattern.** The current template uses CloudFront Origin Access Identities rather than the newer Origin Access Control (OAC) feature. OAIs are fully supported but AWS recommends migrating to OAC for new deployments. This migration is tracked as a future improvement.
