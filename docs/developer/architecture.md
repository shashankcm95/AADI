# Architecture

Arrive is a GPS-powered dine-in ordering and just-in-time kitchen orchestration platform. Its architecture is serverless, event-driven, and designed for independent service deployment. This document explains how the system is structured, why it is structured that way, and how a request flows from the client to the database and back.

## System Overview

```
                          +---------------------+
                          |     CloudFront       |
                          |  (Static Hosting)    |
                          +----------+----------+
                                     |
                    +----------------+----------------+
                    |                                 |
              customer-web                     admin-portal
              (React/Vite)                   (React/Vite/TS)
                    |                                 |
                    +----------------+----------------+
                                     |
                              HTTP API Gateway
                           (Cognito JWT Authorizer)
                                     |
              +----------+-----------+-----------+----------+
              |          |           |           |          |
           Orders    Restaurants   Users     POS HTTP API
           Lambda      Lambda     Lambda    (API Key Auth)
              |          |           |           |
              +----------+-----------+-----------+
                                     |
                               DynamoDB Tables
                                     |
                    +----------------+----------------+
                    |                |                |
                 S3 Buckets    Amazon Location   EventBridge
              (images/avatars)   (geofencing)     (geofence
                                                   events)
```

The platform is built entirely on AWS managed services. There are no EC2 instances, no containers, and no long-running processes. Every compute unit is an AWS Lambda function that starts on demand, processes a single HTTP request, and shuts down.

## The Serverless Model

All backend compute runs on AWS Lambda with Python 3.11 on the arm64 architecture. Each function has a 15-second timeout and 256 MB of memory. These constraints are intentional: they force handlers to be fast and focused, and they keep costs proportional to actual usage rather than provisioned capacity. The arm64 architecture was chosen for its better price-performance ratio compared to x86_64; Lambda functions running on Graviton2 processors are approximately 20% cheaper at equivalent performance.

X-Ray tracing is enabled globally across all Lambda functions and API Gateway stages. This means every request generates a trace that can be followed through API Gateway, into the Lambda function, and down to DynamoDB calls. Combined with the structured JSON logging (described below), this gives operators two complementary views of system behavior: traces for latency analysis and logs for business logic debugging.

The HTTP API Gateway sits in front of all Lambda functions. It handles TLS termination, request routing, and JWT validation. The gateway uses the HTTP API (v2) variant rather than the REST API (v1) because HTTP APIs are lower-latency, lower-cost, and natively support JWT authorizers without a custom Lambda authorizer. The gateway is configured with a Cognito JWT authorizer that validates tokens before the request ever reaches Lambda code. This means that by the time a Lambda handler executes, the caller's identity has already been verified at the infrastructure level.

The POS Integration service is an exception. It uses a separate HTTP API Gateway without the Cognito authorizer, because POS systems authenticate with API keys rather than JWTs. This separation keeps the two authentication models cleanly isolated. The POS HTTP API includes throttling configuration (burst limit of 100 requests, steady-state rate of 50 requests per second) to protect the backend from abusive POS integrations.

## Service Boundaries

The backend is divided into four services, each deployed as a single Lambda function that handles all routes for its domain. This is the "Lambda-lith" pattern: one function per service, with internal routing handled by a Python router module (`app.py`).

**Orders Service** owns the order lifecycle. It manages order creation, status transitions, capacity gating, location ingestion, vicinity updates, arrival tracking, and order expiry. It is the most complex service and contains the core business logic of the platform. The orders service reads restaurant configuration from the shared `RestaurantConfigTable` but never writes to restaurant-owned tables.

**Restaurants Service** owns restaurant profiles, menus, configuration, images, geofencing setup, and customer favorites. It handles the admin-facing operations: creating and updating restaurants, managing menus and pricing, configuring capacity limits and dispatch triggers. It also serves public read endpoints for listing restaurants and fetching menus.

**Users Service** owns user profiles and avatar uploads. It is the simplest service, handling profile reads and updates plus S3 presigned URL generation for avatar uploads. The Users service is defined inline in the root SAM template rather than as a nested stack, because its resource footprint is small.

**POS Integration Service** bridges external point-of-sale systems with the Arrive platform. It translates POS commands into Arrive order operations, syncs menus between systems, and processes webhooks from POS providers. It authenticates via API keys rather than Cognito JWTs and has a separate HTTP API Gateway. The POS stack is conditionally deployed, controlled by the `DeployPosIntegration` parameter.

### Why These Boundaries?

The service boundaries follow domain ownership. Each service owns its DynamoDB tables and has exclusive write access to them. Cross-service data sharing happens through shared DynamoDB reads: the Orders service reads the `RestaurantConfigTable` to check capacity limits, but only the Restaurants service writes to it. This avoids the need for synchronous inter-service calls and keeps the architecture simple.

There is no service mesh, no message bus between services, and no API-to-API calls. Each service reads directly from DynamoDB tables that another service owns. This is a pragmatic choice for a system at this scale: it eliminates network hops and failure modes at the cost of tighter coupling to the shared data model. If the system needed to scale to many more services, you would introduce an event bus (EventBridge or SNS) for cross-service communication.

## Request Flow

A typical request flows through five layers:

```
Client (browser/mobile)
  |
  v
API Gateway (route matching, JWT validation)
  |
  v
Lambda Handler (app.py router)
  |
  v
Handler Module (business logic)
  |
  v
DynamoDB / S3 / Location Service
```

Here is the concrete flow for a customer creating an order:

1. The React client sends `POST /v1/orders` with a Bearer token in the Authorization header.
2. API Gateway matches the route to the Orders Lambda function. The Cognito JWT authorizer validates the token and injects the decoded claims into the event's `requestContext.authorizer.jwt.claims`.
3. The Lambda handler (`app.py`) extracts the route key (`POST /v1/orders`) and the user's claims. It checks that the caller has the `customer` role.
4. The router dispatches to `handlers/customer.py::create_order()`. This function validates the request body, checks idempotency, looks up restaurant configuration, attempts to reserve a capacity slot, and writes the new order to DynamoDB.
5. The handler returns a response dict with `statusCode`, `headers` (including CORS), and a JSON `body`. Lambda serializes this and returns it through API Gateway to the client.

Every response includes CORS headers. The `cors_headers(event)` function dynamically matches the `Origin` request header against a whitelist derived from the `CORS_ALLOW_ORIGIN` and `CORS_ALLOW_ORIGIN_ADMIN` environment variables, with fallbacks to `localhost:5173` and `localhost:5174` for local development.

## The Shared Lambda Layer

All four services share a common Lambda Layer located at `services/shared/python/shared/`. This layer contains four modules that every handler imports:

**`auth.py`** extracts and normalizes Cognito JWT claims from the API Gateway event. The `get_user_claims(event)` function handles both HTTP API v2 and REST API v1 event formats, returning a consistent dict with `role`, `restaurant_id`, `customer_id`, `user_id`, `username`, and `email`. It applies a fallback: if a user has no explicit role claim but has a `sub` and no `restaurant_id`, they are treated as a `customer`. This handles legacy and federated users.

**`cors.py`** provides dynamic CORS header generation. The `cors_headers(event)` function reads the allowed origins from environment variables, matches the incoming `Origin` header, and returns the appropriate `Access-Control-Allow-Origin`. Every Lambda response passes through this function.

**`logger.py`** provides structured JSON logging compatible with CloudWatch Insights. The `get_logger(name)` function returns a `StructuredLogger` that outputs one JSON object per log line with fields for timestamp, level, logger name, message, service name, and correlation ID. The `extract_correlation_id(event)` function pulls the request ID from the API Gateway event for distributed tracing.

**`serialization.py`** handles JSON serialization of DynamoDB Decimal types and provides the `make_response(status_code, body, event)` helper that constructs a complete Lambda response with CORS headers and a JSON body.

## The Router Pattern

Each service's `app.py` follows the same pattern: a single `lambda_handler(event, context)` function that acts as a router. It extracts the `routeKey` from the event (a string like `POST /v1/orders`), performs authorization checks, and dispatches to the appropriate handler function.

This pattern was chosen over individual Lambda functions per route because it reduces cold start frequency (one function handles all routes), simplifies deployment (one function to update), and keeps related authorization logic together. The tradeoff is that a change to any handler requires redeploying the entire service's Lambda function.

Authorization happens in the router, not in individual handlers. The router checks the caller's role and, for restaurant-admin users, verifies that the `restaurant_id` in the path matches the `restaurant_id` in their JWT claims. Handlers can assume that the caller has been authorized when they are invoked.

## Error Handling Strategy

Every service router wraps its dispatch logic in a try/except block that catches domain exceptions and translates them to HTTP responses. The Orders service defines a hierarchy of custom exceptions in `errors.py`:

- `ValidationError` maps to `400 Bad Request` for malformed input.
- `NotFoundError` maps to `404 Not Found` for missing orders or restaurants.
- `InvalidStateError` maps to `409 Conflict` for illegal state transitions.
- `ExpiredError` maps to `409 Conflict` for operations on expired orders.

Any unhandled exception is caught by the outermost handler, logged with full stack trace and correlation ID, and returned as a `500 Internal Server Error`. This ensures that the client always receives a valid JSON response with CORS headers, even on unexpected failures.

The Restaurants and Users services follow the same pattern but with fewer domain exception types, since their logic is simpler. The POS service additionally catches `json.JSONDecodeError` for malformed request bodies and returns a clear `400` response.

## DynamoDB Access Patterns

The choice of DynamoDB as the sole persistence layer shapes the entire data model. DynamoDB is a key-value store with optional sort keys and secondary indexes, not a relational database. This means that queries must be designed upfront around known access patterns rather than written ad-hoc with JOINs.

Each table's key schema and GSIs are chosen to serve specific queries efficiently. The OrdersTable, for example, has four GSIs to support four distinct access patterns: listing by customer, listing by restaurant and status, listing by restaurant and time, and finding expired orders. Without these indexes, each query would require a full table scan.

All tables use on-demand capacity mode, which means DynamoDB automatically scales throughput based on actual traffic. There is no capacity planning, no provisioned read/write units, and no throttling during traffic spikes (within AWS account limits). This matches the serverless philosophy: pay for what you use, scale automatically.

Point-in-Time Recovery (PITR) is enabled on every table. This provides continuous backups that can be restored to any second within the past 35 days. PITR is a safety net against data corruption, accidental deletes, and bad deployments.

## Observability

The platform is designed to be observable through three channels: structured logs, distributed traces, and CloudWatch metrics.

**Structured Logs** are emitted as single-line JSON objects by the `StructuredLogger` from the shared layer. Each log entry includes a timestamp, log level, logger name, message, service name, and correlation ID. Handler-specific fields (order_id, restaurant_id, customer_id, duration_ms) are attached as structured context. CloudWatch Insights can query these fields directly:

```
fields @timestamp, level, correlation_id, order_id, message
| filter level = "ERROR"
| sort @timestamp desc
```

Every request is bracketed by a `request_received` log at entry and a `request_completed` log at exit. The completion log includes `duration_ms`, enabling latency analysis directly from logs.

**Distributed Traces** via AWS X-Ray are enabled on all Lambda functions and API Gateway stages. X-Ray traces show the end-to-end latency of a request, including time spent in DynamoDB calls and any external service calls. This is particularly useful for diagnosing cold start latency and identifying slow DynamoDB queries.

**CloudWatch Metrics** are collected automatically by Lambda and API Gateway. Key metrics include invocation count, error rate, duration, and throttle count. These can be used to build dashboards and alarms for operational monitoring.

## Frontend Architecture

The frontend consists of three applications that share no code with each other:

**Customer Web** (`packages/customer-web/`) is a React single-page application built with Vite. It handles restaurant browsing, menu viewing, order placement, and real-time order tracking. It authenticates via Cognito and communicates with the backend through the HTTP API Gateway.

**Admin Portal** (`packages/admin-portal/`) is a React application built with Vite and TypeScript. It provides restaurant management, menu editing, order monitoring, configuration, and POS settings. It runs on a separate port (5174) and uses a separate CORS origin.

**Mobile iOS** (`packages/mobile-ios/`) is a React Native application built with Expo. It provides the same customer-facing functionality as the web app plus GPS-based location tracking for arrival detection. The mobile app publishes device positions to the Amazon Location Service tracker for geofence evaluation.

All three applications are hosted on S3 behind CloudFront in production. The CloudFront distribution handles HTTPS, caching, and routing SPA requests to `index.html`.

The frontend applications share no code with the backend. They communicate exclusively through the HTTP API Gateway using JSON over HTTPS. Configuration (API endpoint URLs, Cognito User Pool IDs) is injected through `aws-exports.js` files generated during deployment. This clean separation means frontend and backend can be developed and deployed independently.

## Geofencing and Location Tracking

The arrival detection pipeline uses Amazon Location Service with three components:

**LocationTracker** receives GPS positions from the mobile app. Positions are published via the `batch_update_device_position` API. The tracker uses `AccuracyBased` filtering to reduce noise and API costs.

**LocationGeofenceCollection** stores three concentric geofence zones per restaurant, each defined as a circle polygon: `arrive` (closest), `nearby` (medium), and `vicinity` (farthest). The geofence IDs encode both the restaurant and the zone, formatted as `{restaurant_id}|{event_name}` (for example, `rest_abc|5_MIN_OUT`).

**EventBridge Rule** triggers the `GeofenceEventsFunction` when a device enters a geofence. The function parses the geofence ID to determine the restaurant and arrival event, finds the customer's active order, and either records a shadow event or triggers a dispatch transition depending on the cutover flag.

The system operates in shadow mode by default (`LocationGeofenceCutoverEnabled=false`). In shadow mode, geofence events are recorded on the order as metadata but do not trigger status transitions. This allows the geofence accuracy to be validated against client-reported vicinity updates before the system relies on it for dispatching.

## Infrastructure as Code

The entire infrastructure is defined in `infrastructure/template.yaml` using AWS SAM (an extension of CloudFormation). The root template creates shared resources and nests child stacks:

- **Cognito User Pool and Client** with Google federated identity
- **CloudFront Distribution** for frontend hosting
- **S3 Buckets** for restaurant images and user avatars
- **Amazon Location Service** tracker and geofence collection
- **EventBridge Rule** for geofence events
- **Shared Lambda Layer** published from `services/shared/python/`
- **Nested Stacks** for Orders, Restaurants, and (conditionally) POS Integration
- **Inline Resources** for the Users service

The nested stack pattern keeps each service's resources (Lambda function, DynamoDB tables, IAM policies) grouped together while allowing the root stack to wire them together with shared references like the Cognito User Pool ARN and table names.

## Design Principles

Several principles guide the architecture:

**Fail closed.** Authorization defaults to denial. If JWT claims are missing, the request is rejected. If a POS API key has no permissions array, it has no permissions. If a role is unrecognized, access is denied.

**Idempotency.** Order creation uses an `Idempotency-Key` header backed by a DynamoDB table with TTL. Duplicate requests within the TTL window return the original order rather than creating a new one. Status transitions use DynamoDB conditional writes to prevent concurrent conflicting updates.

**Capacity isolation.** The capacity system uses DynamoDB atomic counters with conditional expressions to enforce per-restaurant, per-time-window limits. This provides strong consistency without distributed locks.

**Observable by default.** Every request is logged as structured JSON with a correlation ID. CloudWatch Insights can query across all services using the correlation ID to trace a request end-to-end. X-Ray tracing is enabled on all Lambda functions and API Gateway stages.

**Progressive rollout.** Features like geofence-based dispatching use feature flags (`LocationGeofenceCutoverEnabled`, `LocationGeofenceForceShadow`) that can be toggled per deployment without code changes. The POS integration stack itself is conditionally deployed via a SAM parameter.

## Deployment Model

The entire backend deploys as a single SAM application. The `sam build` command packages each Lambda function and the shared layer, and `sam deploy` pushes the CloudFormation stack to AWS. Because every service is part of the same SAM template (either as nested stacks or inline resources), a deployment is atomic: all services update together or none do.

The nested stack pattern provides a balance between isolation and coordination. Each nested stack (Orders, Restaurants, POS) defines its own Lambda function, DynamoDB tables, and IAM policies. The root stack passes shared references (Cognito User Pool ARN, table names, S3 bucket names) as parameters to the nested stacks. If a service needs access to another service's table, the root stack passes the table name as a parameter.

Frontend deployment is separate from backend deployment. The `deploy_customer_app.sh` and `deploy_admin_stack.sh` scripts build the applications, upload the built assets to S3, and optionally invalidate the CloudFront cache. This means frontend changes can be deployed without touching the backend, and vice versa.

## Scaling Characteristics

The system scales automatically along every dimension. Lambda functions scale horizontally by spinning up new instances for concurrent requests. DynamoDB scales throughput on-demand. API Gateway has no practical throughput limit. S3 and CloudFront scale to any request volume.

The primary scaling bottleneck is the capacity system, which is deliberately limited. The capacity gating uses DynamoDB conditional writes, which are strongly consistent and serialized per item. This means that for a given restaurant and time window, capacity reservation requests are effectively serialized. At very high concurrency (hundreds of simultaneous orders for the same restaurant in the same 5-minute window), this could become a hot partition. In practice, this is the desired behavior: the capacity limit exists precisely to prevent restaurants from being overwhelmed.

Lambda cold starts are the other consideration. The Lambda-lith pattern (one function per service) reduces cold start frequency compared to one-function-per-route, because any request to the service warms the same function. With 256 MB of memory and Python 3.11 on arm64, typical cold starts are under 1 second. The 15-second timeout provides ample headroom for both warm and cold invocations.
