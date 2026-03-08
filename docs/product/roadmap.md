# Arrive Platform Roadmap

## Current State: What Is Built Today

The Arrive platform is a fully functional dine-in restaurant ordering system with location-aware dispatch. As of this writing, the platform has completed a comprehensive development phase that includes all core services, all frontends, a full test suite, and a rigorous security hardening process.

### Backend Services

Four backend services are implemented, tested, and deployable via AWS SAM and CloudFormation. The Orders Service handles the complete order lifecycle, including the location-aware dispatch engine, capacity gating with atomic DynamoDB counters, geofence event processing via EventBridge, and order expiration. The Restaurants Service manages restaurant profiles, menus (with Decimal precision pricing and CSV/Excel import), image uploads via S3 presigned URLs, geofence zone configuration, and customer favorites. The Users Service provides profile management and avatar uploads. The POS Integration Service offers a full API for third-party point-of-sale systems, including order creation, status updates, menu synchronization, webhook ingestion with idempotency, and force-fire capability.

### Frontend Applications

Three frontends are functional and communicating with the backend APIs. The Customer Web Application (React/Vite) supports restaurant browsing, menu viewing, cart management, dine-in order placement, order tracking, and profile management. The Admin Portal (React/TypeScript/Vite) provides a Kanban-style order management board with real-time polling, audio notifications for new orders, auto-promotion of stale incoming orders, menu ingestion, capacity configuration, image management, and POS settings. The Mobile iOS Application (React Native/Expo) delivers the customer experience with the addition of GPS-based location tracking that powers the dispatch engine.

### Quality and Security

The platform has 467 automated tests covering unit tests, integration tests, component tests, and end-to-end lifecycle tests. A continuous integration pipeline runs linting (ruff), security scanning (detect-secrets), and the full test suite on every push. The codebase underwent a 14-phase systematic code review that identified and resolved all 70 backlog items spanning security vulnerabilities, correctness bugs, performance issues, and reliability gaps.

Security measures in place include SHA-256 hashing of POS API keys at rest, scoped IAM policies without resource wildcards, S3 buckets with public access blocked, environment-driven CORS origin validation, Cognito email validation against filter injection, and API Gateway throttling on the POS integration endpoint (burst limit of 100, sustained rate of 50 requests per second).


## Near-Term: Production Readiness

The near-term roadmap focuses on closing the gap between the current development state and a live production deployment.

### Geofence Cutover

The geofencing infrastructure is fully built and operational in shadow mode. Geofence zones are defined per restaurant in AWS Location Service, EventBridge rules route entry events to the Orders Service, and the event processing pipeline correctly matches events to orders and records them. The next step is to enable live cutover by setting the LOCATION_GEOFENCE_CUTOVER_ENABLED environment variable. Before cutover, the shadow event data that has been accumulating will be analyzed to validate zone accuracy and tune the default radii (currently 1,500 meters, 150 meters, and 30 meters) for typical restaurant environments.

### POS Integration Production Deployment

The POS Integration Service is code-complete and tested, but it has not yet been deployed to a live restaurant with a real POS system. The near-term plan is to partner with an initial restaurant using one of the supported POS providers (Square, Toast, Clover, or a custom integration) to validate the end-to-end flow: order creation from POS, status updates bidirectionally, menu synchronization, and webhook delivery.

### WAF and Broader API Throttling

The POS integration endpoint already has API Gateway throttling configured. The next step is to extend this protection to all public-facing APIs by deploying an AWS WAF (Web Application Firewall) with rate limiting, SQL injection prevention, and common exploit protection rules. This will provide defense-in-depth against abuse and denial-of-service attacks across the entire platform, not just the POS surface.

### Production Monitoring and Alerting

While structured logging is in place across all services (via the shared logger module), production-grade monitoring requires CloudWatch dashboards, alarm thresholds for error rates and latency, and integration with an incident notification system. This work includes setting up the CloudWatch observability stack that has been partially scripted in the Orders Service.


## Mid-Term: Feature Expansion

The mid-term roadmap expands the platform's capabilities to improve the user experience, broaden the authentication options, and make the capacity system smarter.

### Push Notifications

Currently, the mobile app and web application poll the backend every five seconds to check for order status updates. This works but is wasteful and introduces latency. The mid-term plan is to implement push notifications using a combination of AWS SNS (Simple Notification Service) for mobile push and WebSocket connections (via API Gateway WebSocket APIs) for real-time web updates. Customers will receive push notifications when their order status changes -- for example, when the kitchen starts preparing their order, when the food is ready, and when the order is marked for fulfillment. Restaurant staff will receive push notifications for new incoming orders, reducing dependence on the polling-based Kanban board.

### Google OAuth Sign-In

The Cognito user pool is already configured with parameters for a Google OAuth identity provider, but the provider has not been provisioned. Enabling Google sign-in will reduce friction for new customers by allowing them to create an account and log in with their existing Google credentials rather than managing a separate email and password. The implementation involves provisioning the Google IdP in Cognito, configuring the OAuth callback URLs, and updating the frontend sign-in flows to offer a "Sign in with Google" option alongside email/password.

### Adaptive Capacity

The current capacity system uses a fixed configuration per restaurant: a maximum number of concurrent orders within a fixed time window (default 10 orders per 300 seconds). This is functional but static. The mid-term plan is to introduce adaptive capacity that learns from historical patterns. By analyzing past order volumes, preparation times, and completion rates, the system can dynamically adjust capacity limits based on time of day, day of week, and seasonal trends. A restaurant that is consistently slower during lunch rush could automatically have its capacity reduced during those hours, while a restaurant that handles orders faster on weekday mornings could have its capacity increased.

### Real-Time Kitchen Display Integration

Beyond the web-based Admin Portal, many restaurants use dedicated kitchen display systems (KDS) mounted in the kitchen. The mid-term plan is to develop a dedicated KDS interface -- either as a standalone web application optimized for large touchscreens or as an integration layer that pushes order data to third-party KDS hardware. This would allow the kitchen to see incoming orders, mark preparation progress, and update statuses without switching between their KDS and the Arrive Admin Portal.


## Long-Term: Platform Evolution

The long-term roadmap transforms Arrive from a single-location ordering tool into a comprehensive restaurant operations platform.

### Multi-Location Restaurant Chains

The current architecture assumes each restaurant is an independent entity with its own configuration, menu, and order queue. For restaurant chains, this means each location must be configured separately. The long-term plan is to introduce a chain management layer that allows a parent organization to manage multiple locations from a single interface, share menus across locations (with per-location overrides for pricing and availability), aggregate analytics across all locations, and manage staff access at the chain level.

### Payment Processing Integration

Arrive currently operates on a PAY_AT_RESTAURANT model, where the platform calculates the order total and an Arrive platform fee (2% split between restaurant and customer) but does not collect payment. The long-term plan is to integrate with a payment processor (such as Stripe Connect) to enable in-app payment, split the platform fee at checkout, support tipping, and handle refunds for canceled orders. This is a significant architectural addition that involves PCI compliance considerations, payment state management, and integration with the order lifecycle state machine.

### Takeout and Delivery Expansion

The current platform focuses exclusively on dine-in table service. A future expansion could explore takeout ordering and delivery coordination by introducing a driver management layer, but this is not part of the current product vision. The existing dispatch engine and capacity system could be adapted to coordinate delivery timing, but significant new capabilities (driver assignment, route optimization, delivery tracking) would need to be built.

### Analytics Dashboard

Restaurants currently have visibility into their active orders through the Kanban board, but they lack historical analytics. The long-term plan is to build an analytics dashboard that provides insights into order volume trends, average preparation times, peak hours, customer return rates, capacity utilization, and revenue tracking. This data is already captured in DynamoDB (timestamps are recorded at every status transition), so the work is primarily in building the aggregation pipeline and the visualization layer.

### Menu Intelligence

As the platform accumulates data on order patterns, there is an opportunity to provide menu intelligence to restaurants: identifying which items are most popular, which items are frequently ordered together, which items have high preparation-time variance, and which items contribute most to kitchen bottlenecks. This information can help restaurants optimize their menus for both customer satisfaction and operational efficiency.


## Technical Debt: Resolved

The 14-phase code review systematically addressed all identified technical debt in the codebase. All 70 backlog items have been resolved, spanning categories including security vulnerabilities (Cognito filter injection, IAM wildcard policies, POS key storage, S3 CORS wildcards), correctness bugs (race conditions in order cancellation, silent item drops in menu updates, missing CORS headers), performance issues (S3 client created per invocation, full-table scans on GSI fallback), reliability gaps (missing error handling, weak test assertions), and infrastructure concerns (deprecated CloudFront configurations, unused deployment scripts, hardcoded environment values).

The codebase is in a clean state with no known unresolved issues. Future development will continue to follow the established patterns -- structured logging, shared utility layers, comprehensive test coverage, and infrastructure-as-code -- to maintain this quality baseline.
