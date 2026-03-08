# Infrastructure Guide

This document describes the cloud infrastructure that underpins the Arrive platform. Every resource is defined as code in AWS CloudFormation templates using the AWS Serverless Application Model (SAM) transform. The infrastructure follows a root-plus-nested-stacks pattern, with a single root template orchestrating shared resources and delegating service-specific resources to child stacks.

---

## Stack Architecture

The entire backend is deployed as a single CloudFormation stack with nested child stacks. The root template lives at `infrastructure/template.yaml`. It creates resources that are shared across multiple services (Cognito, CloudFront, S3 hosting, Amazon Location, the shared Lambda layer) and then instantiates three mandatory child stacks and one conditional child stack.

The **UsersService** child stack is defined at `services/users/template.yaml`. The **RestaurantsService** child stack is defined at `services/restaurants/template.yaml`. The **OrdersService** child stack is defined at `services/orders/template.yaml`. The **PosIntegrationService** child stack is defined at `services/pos-integration/template.yaml` and is only created when the `DeployPosIntegration` parameter is set to `true`.

Each child stack is declared as an `AWS::Serverless::Application` resource in the root template. SAM resolves the relative `Location` path to the child template, packages it, and uploads it to S3 during `sam deploy`. The root stack passes configuration to each child via the `Parameters` property, which maps root-level values (Cognito IDs, CORS origins, resource ARNs, shared layer ARN) to the child stack's own parameter declarations.

Child stacks expose key resource names and API endpoint URLs via their `Outputs` section. The root stack reads these outputs using `!GetAtt` intrinsic functions. For example, the OrdersService receives the `RestaurantConfigTableName` from the RestaurantsService outputs, allowing the Orders Lambda to perform cross-service reads against the restaurant configuration table.

---

## DynamoDB Tables

Arrive uses DynamoDB as its sole database layer. All tables use on-demand billing (`PAY_PER_REQUEST`) to avoid capacity planning overhead, and every table has point-in-time recovery enabled for data protection. Many tables also have TTL attributes for automatic record expiry.

### Orders Stack Tables

**OrdersTable** stores every order in the system. The partition key is `order_id` (string). It has four global secondary indexes: `GSI_RestaurantStatus` (partitioned by `restaurant_id`, sorted by `status`) for restaurant dashboards to query orders by state; `GSI_RestaurantCreated` (partitioned by `restaurant_id`, sorted by `created_at`) for time-ordered restaurant order history; `GSI_CustomerOrders` (partitioned by `customer_id`, sorted by `created_at`) for customer order history; and `GSI_StatusExpiry` (partitioned by `status`, sorted by `expires_at`, keys-only projection) used by the expiry Lambda to find abandoned orders. A TTL attribute named `ttl` is enabled for automatic cleanup of old records.

**CapacityTable** tracks order capacity per restaurant per time window. The partition key is `restaurant_id` and the sort key is `window_start` (number, epoch seconds). Each item represents a capacity slot and is cleaned up by a TTL attribute.

**IdempotencyTable** prevents duplicate order creation. The partition key is `idempotency_key` (string), and a TTL attribute ensures keys expire after a reasonable window.

**GeofenceEventsTable** stores deduplication records for Amazon Location geofence events. The partition key is `event_id`, and TTL is enabled. This table ensures that duplicate ENTER events from EventBridge do not trigger multiple order state transitions.

### Restaurants Stack Tables

**RestaurantsTable** is the primary restaurant registry. The partition key is `restaurant_id`. It has three GSIs: `GSI_ActiveRestaurants` (partitioned by `is_active`, sorted by `name`) for listing active restaurants; `GSI_Cuisine` (partitioned by `cuisine`, sorted by `name`) for filtering by cuisine type; and `GSI_PriceTier` (partitioned by `price_tier`, sorted by `name`) for filtering by price range.

**RestaurantConfigTable** stores per-restaurant configuration such as preparation times, geofence radii, and operating hours. The partition key is `restaurant_id`. This table is shared read-only with the Orders service to validate restaurant configuration during order creation.

**MenusTable** stores restaurant menus with versioning. The partition key is `restaurant_id` and the sort key is `menu_version` (string). This composite key allows historical menu versions to coexist alongside the current active version.

**FavoritesTable** tracks customer restaurant favorites. The partition key is `customer_id` and the sort key is `restaurant_id`, forming a many-to-many relationship.

### Users Stack Tables

**UsersTable** stores user profile data. The partition key is `user_id` (the Cognito `sub` claim). Profile fields include display name, phone number, and avatar URL.

### POS Stack Tables

**PosApiKeysTable** stores SHA-256 hashed API keys for POS system authentication. The partition key is `api_key` (the hash, not the plaintext). Each item contains `restaurant_id`, `pos_system`, `permissions`, and an optional `ttl` for key expiry.

**PosWebhookLogsTable** logs inbound POS webhook events for auditing and debugging. The partition key is `webhook_id`, and TTL is enabled for automatic cleanup.

---

## S3 Buckets

Arrive provisions four S3 buckets, all with full public access blocking enabled (`BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, `RestrictPublicBuckets` all set to `true`).

**CustomerWebBucket** hosts the customer-facing React SPA. It is configured for static website hosting with `index.html` as both the index and error document (to support client-side routing). Access is granted exclusively through a CloudFront Origin Access Identity (OAI); direct S3 access is blocked.

**AdminPortalBucket** hosts the admin portal React SPA with the same configuration pattern as the customer web bucket.

**RestaurantImagesBucket** stores restaurant media assets (logos, photos). It is not a website bucket. Access is controlled via IAM policies on the Restaurants Lambda function, which generates presigned PUT URLs for uploads and presigned GET URLs for reads. The bucket has S3 CORS rules allowing GET, PUT, and HEAD requests from the configured CORS origins.

**UserAvatarsBucket** stores user profile avatar images. Like the restaurant images bucket, it is not publicly accessible. The Users Lambda generates presigned URLs for upload and retrieval. CORS rules mirror those of the restaurant images bucket.

---

## CloudFront Distributions

Two CloudFront distributions serve the frontend applications.

**CustomerWebDistribution** points to the CustomerWebBucket via an OAI. It enforces HTTPS by redirecting HTTP requests, uses the AWS managed `CachingOptimized` cache policy (no query string or cookie forwarding), and applies the AWS managed `SecurityHeadersPolicy` which adds HSTS, X-Content-Type-Options, and X-Frame-Options headers. Custom error responses map both 403 and 404 errors to `/index.html` with a 200 status code, which is necessary for client-side routing in the SPA.

**AdminPortalDistribution** has an identical configuration pointing to the AdminPortalBucket. It uses the same cache policy and security headers policy.

Both distributions use the default CloudFront domain names (e.g., `d1234abcdef.cloudfront.net`). Custom domain names with ACM certificates can be added but are not configured in the current template.

---

## API Gateway HTTP APIs

Each service group has its own API Gateway HTTP API, providing independent scaling, monitoring, and authorization configuration.

The **Orders HTTP API** is created implicitly by SAM from the `HttpApi` event sources on the OrdersFunction. It uses the Cognito JWT authorizer as its default authorizer. CORS is configured to allow the customer-web origin, admin-portal origin, and both localhost development ports. Allowed headers include `Authorization`, `Content-Type`, and `Idempotency-Key`.

The **Restaurants HTTP API** follows the same pattern, with CORS additionally allowing `PUT` and `DELETE` methods for restaurant management operations.

The **Users HTTP API** also follows the same pattern. Notably, the `/v1/users/health` route has `Auth: Authorizer: NONE`, making it the only unauthenticated endpoint on this API for health checking purposes.

The **POS HTTP API** is fundamentally different. It does not use a Cognito JWT authorizer at all. Instead, it is a plain HTTP API with no built-in authorization. Authentication is handled at the application level by the POS Lambda function, which extracts the `X-POS-API-Key` header and validates it against the PosApiKeysTable. This API has throttle limits configured at 100 burst and 50 requests per second to protect downstream DynamoDB capacity.

---

## Cognito User Pool

The `ArriveCognitoUserPool` (resource name `UserPool`) is the identity provider for all customer and admin users. It is configured with email-based sign-up (`UsernameAttributes: email`), automatic email verification, and a password policy requiring a minimum of 8 characters with uppercase, lowercase, numbers, and symbols.

The schema defines two custom attributes: `custom:role` (which holds one of `customer`, `restaurant_admin`, or `admin`) and `custom:restaurant_id` (which links a restaurant_admin to their specific restaurant). These custom attributes are set by the PostConfirmation trigger or by admin operations.

The **PostConfirmationFunction** is a Lambda trigger that fires after a user confirms their email. It automatically assigns the `customer` role to new users by writing to the UsersTable and updating the Cognito user attributes. Due to a circular dependency (the User Pool needs the Lambda ARN, but the Lambda needs the User Pool ID), the trigger is attached via a CloudFormation Custom Resource (`AttachPostConfirmationTrigger`) rather than being declared directly in the User Pool's `LambdaConfig`.

A dead-letter queue (`PostConfirmationDLQ`) captures failed PostConfirmation invocations after 2 retry attempts, ensuring that trigger failures are visible and can be investigated.

The **UserPoolClient** supports the authorization code and implicit OAuth flows, with scopes for `email`, `openid`, and `profile`. Callback and logout URLs include both localhost development URLs and the CloudFront distribution domains.

---

## Amazon Location Resources

Arrive uses Amazon Location Service for geofence-based arrival detection.

**LocationTracker** is an Amazon Location tracker with accuracy-based position filtering and EventBridge integration enabled. Mobile clients report device positions to this tracker, and it evaluates positions against linked geofence collections.

**LocationGeofenceCollection** stores circular geofences centered on restaurant locations. Each geofence is identified by a restaurant-specific key and has a configurable radius.

**LocationTrackerConsumer** links the tracker to the geofence collection, so position updates are automatically evaluated against all geofences in the collection.

When a device enters a geofence, Amazon Location emits a `Location Geofence Event` with `EventType: ENTER` to EventBridge. The OrdersService's `GeofenceEventsFunction` subscribes to these events via a CloudWatch Event rule and processes them to potentially transition order state.

---

## IAM Roles and Least-Privilege Design

Every Lambda function in the stack receives an IAM execution role generated by SAM with only the permissions it needs. The platform follows a strict least-privilege model that was enforced during a 14-phase security review.

Lambda functions use SAM policy templates (`DynamoDBCrudPolicy`, `DynamoDBReadPolicy`, `S3CrudPolicy`, `SQSSendMessagePolicy`) wherever possible. These templates scope permissions to specific table or bucket ARNs. Where SAM templates are insufficient, inline policy statements grant specific actions on specific resource ARNs.

For example, the OrdersFunction has `DynamoDBCrudPolicy` on OrdersTable, CapacityTable, and IdempotencyTable, but only `DynamoDBReadPolicy` on RestaurantConfigTable because it reads but never writes restaurant configuration. Its Location Service permission is scoped to `geo:BatchUpdateDevicePosition` on the specific tracker ARN.

The RestaurantsFunction has Cognito permissions (`AdminCreateUser`, `AdminSetUserAttributes`, `ListUsers`, `AdminDeleteUser`) scoped to the specific User Pool ARN, not a wildcard. Its S3 permissions are scoped to the specific images bucket. Its Location permissions are scoped to the specific geofence collection ARN.

The POS Integration function has explicit `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, and `dynamodb:Query` permissions on the cross-service tables (Orders, Menus, Capacity), with each permission scoped to the specific table ARN and its indexes. It does not have `dynamodb:Scan` permission.

---

## The Shared Lambda Layer

The shared Lambda layer (`SharedLayer`) is declared in the root template and built from `services/shared/`. It provides four Python modules available to every Lambda function in the stack:

`shared.auth` provides JWT claim extraction from API Gateway events, supporting both HTTP API v2 and REST API v1 event formats. `shared.cors` provides dynamic CORS header generation based on the request origin. `shared.logger` provides structured JSON logging via a custom `structlog`-style adapter. `shared.serialization` provides JSON serialization utilities for DynamoDB Decimal types and other non-standard Python objects.

The layer is pinned to Python 3.11 and arm64 architecture. It uses a `Retain` retention policy, meaning old layer versions are not deleted when a new version is published, allowing rollback.

---

## How Nested Stacks Reference Each Other

The flow of data between stacks follows a strict parent-mediated pattern. Child stacks never reference each other directly. Instead, the root stack reads outputs from one child and passes them as parameters to another.

The RestaurantsService outputs its `RestaurantConfigTableName`. The root stack reads this with `!GetAtt RestaurantsService.Outputs.RestaurantConfigTableName` and passes it to the OrdersService as the `RestaurantConfigTableName` parameter. Similarly, when POS Integration is enabled, the root stack reads `OrdersTableName` and `CapacityTableName` from OrdersService and `MenusTableName` from RestaurantsService, then passes all three to PosIntegrationService.

CORS origins flow from the root stack's CloudFront distribution domain names to each child via `CorsAllowOrigin` and `CorsAllowOriginAdmin` parameters. Cognito identifiers (`UserPoolId`, `UserPoolClientId`) flow from the root to each child stack that needs JWT authorization. The shared layer ARN flows from `!Ref SharedLayer` in the root to each child's `SharedLayerArn` parameter.

This mediated pattern avoids circular dependencies and keeps each child stack independently deployable for local testing with `sam local`.
