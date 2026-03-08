# Arrive Platform Overview

## The Problem: Timing Is Everything

Every day, millions of restaurant orders suffer from the same fundamental problem: the kitchen has no idea when the customer will actually walk through the door. A customer places an order, and the restaurant starts cooking immediately -- but the customer might be five minutes away or thirty. The food sits. Fries get cold. Ice melts. Alternatively, the kitchen holds off, the customer walks in, and now they are waiting while their order is prepared from scratch.

The root cause is simple: traditional ordering systems treat the restaurant and the customer as two disconnected parties. There is no coordination between when the food will be ready and when the customer will actually arrive. The restaurant has no visibility into the customer's location. The customer has no visibility into kitchen capacity. Everyone is operating on guesswork.

Arrive solves this by introducing real-time location awareness into the ordering process. Customers place their order ahead of time -- from home, from work, from wherever they are. The platform holds the order while the customer goes about their day. When the customer starts heading to the restaurant, the Arrive app tracks their approach and dispatches the order to the kitchen at precisely the right moment. The customer walks in, identifies themselves, sits down, and their food is served fresh to the table. No waiting to order. No waiting for food. The customer's travel time becomes the kitchen's prep time.


## How Arrive Works

Arrive is a three-sided coordination platform that connects customers, restaurants, and a location-aware dispatch engine into a unified workflow. The platform operates across web, mobile, and point-of-sale touchpoints, and it uses geofencing technology to bridge the gap between when food is ordered and when the customer arrives for their dine-in meal.

### The Customer Experience

A customer opens the Arrive app on their phone or visits the web application. They browse nearby restaurants, explore menus, and add items to their cart. When they confirm their order, the platform does not immediately fire that order to the kitchen. Instead, it holds the order in a pending state while the customer goes about their day.

When the customer is ready to head to the restaurant, they start their journey. The Arrive mobile app tracks their location (with their explicit permission) and detects when they cross into the restaurant's geofence zones. As the customer approaches -- typically about five minutes away -- the platform dispatches the order to the restaurant. The kitchen begins preparation, calibrated to the customer's arrival.

The customer walks in, lets the staff know who they are, and sits down at their table. Their food is freshly prepared and arrives at the table within moments. There is no waiting to place an order, no waiting for the kitchen -- the travel time was the prep time.

### The Restaurant Experience

On the restaurant side, Arrive replaces the chaos of uncoordinated orders with a predictable, manageable flow. Orders do not arrive in random bursts that overwhelm the kitchen. Instead, they are dispatched through a capacity-gated system that respects the restaurant's throughput limits.

Each restaurant configures its maximum concurrent orders -- the number of orders the kitchen can handle simultaneously within a given time window. The default is ten orders per five-minute window, but this is fully adjustable. When the capacity window is full, incoming orders are queued and dispatched as soon as a slot opens up. This prevents the kitchen from being overwhelmed and ensures consistent food quality.

Restaurant staff interact with Arrive through the Admin Portal, a web-based dashboard that displays incoming orders on a Kanban-style board. Orders flow through clear status lanes -- Incoming, In Progress, Ready, Fulfilling, and Completed -- giving the kitchen a real-time view of what needs attention. The portal plays an audio notification when a new order arrives, and it supports auto-promotion of orders that have been sitting in the incoming lane for too long.

### The Dispatch Engine

The core of Arrive's value proposition is its dispatch engine, a purpose-built system that decides when to send orders to the kitchen based on real-time location data. The engine processes arrival events from the mobile app -- specifically, three progressive proximity signals:

The first signal, "5 Minutes Out," fires when the customer enters the outermost geofence zone, typically about 1,500 meters from the restaurant. This is the default dispatch trigger, and for most restaurants, it provides enough lead time for the kitchen to prepare a standard order.

The second signal, "Parking," fires when the customer enters the middle zone, approximately 150 meters away. Some restaurants with faster preparation times may choose this as their dispatch trigger.

The third signal, "At Door," fires when the customer is within about 30 meters of the restaurant. This is used for restaurants with extremely fast preparation -- think coffee shops or quick-service counters.

Restaurants can configure which zone triggers order dispatch through the Admin Portal's Capacity Settings. The engine also monitors for an "Exit Vicinity" signal, which automatically completes orders when the customer leaves the restaurant after their meal, reducing manual status management for the kitchen.

The dispatch engine enforces capacity constraints using atomic DynamoDB counters. When a dispatch trigger fires, the engine checks whether the restaurant has an available capacity slot in the current time window. If a slot is available, it reserves it atomically and dispatches the order. If all slots are taken, the order enters a "Waiting for Capacity" state and is dispatched as soon as a slot opens. This mechanism is thread-safe and handles concurrent requests without race conditions.


## Platform Architecture

Arrive is built on a fully serverless AWS architecture, designed for operational simplicity, automatic scaling, and minimal infrastructure management. The entire backend runs on AWS Lambda functions orchestrated by API Gateway, with DynamoDB as the primary data store, Cognito for authentication, S3 for file storage, and CloudFront for content delivery.

### Backend Services

The platform is composed of four independent backend services, each deployed as a separate CloudFormation nested stack within a root SAM template.

The **Orders Service** is the heart of the platform. It manages the complete order lifecycle from creation through completion, runs the dispatch engine, handles capacity gating, processes location updates from the mobile app, and consumes geofence events from AWS Location Service via EventBridge. It exposes separate API endpoints for customer-facing operations (placing orders, updating location, canceling) and restaurant-facing operations (acknowledging orders, updating status, viewing active orders).

The **Restaurants Service** manages everything related to restaurant configuration, menus, and imagery. It handles restaurant creation and updates, menu management with full CRUD operations, image uploads via S3 presigned URLs, restaurant configuration (capacity settings, geofence zones, POS preferences), and customer favorites. Menu prices are stored with Decimal precision using banker's rounding (ROUND_HALF_UP) to avoid floating-point errors, and each menu item carries both a human-readable price and a machine-safe price_cents integer.

The **Users Service** manages customer profiles and avatar uploads. It provides endpoints for creating and updating user profiles, uploading profile pictures via S3 presigned URLs, and retrieving user information. Profile pictures are stored in a dedicated S3 bucket with public access blocked; images are served through presigned URLs with time-limited access.

The **POS Integration Service** provides an API for third-party point-of-sale systems to interact with the Arrive platform. POS systems authenticate using API keys (transmitted in the X-POS-API-Key header) rather than Cognito tokens. Keys are stored as SHA-256 hashes in DynamoDB -- the plaintext key is never persisted. The service supports order creation, order listing, status updates, menu synchronization, force-fire (manual dispatch override), and webhook ingestion with idempotency deduplication.

### Frontend Applications

Arrive has three frontend applications, each tailored to a specific user persona.

The **Customer Web Application** is a React single-page application built with Vite. It provides restaurant browsing, menu viewing, cart management, order placement, order tracking, profile management, and a favorites system. It authenticates via AWS Cognito and communicates with the backend through API Gateway HTTP APIs. The web app is deployed to S3 and served through CloudFront.

The **Admin Portal** is a React application built with TypeScript and Vite. It is the primary tool for restaurant managers and platform administrators. Restaurant admins see a dashboard focused on their assigned restaurant, with a Kanban board for order management, menu ingestion (CSV/Excel upload), capacity configuration, image management, and POS settings. Super admins see a broader dashboard with the ability to manage multiple restaurants and invite new restaurant administrators.

The **Mobile iOS Application** is built with React Native and Expo. It provides the full customer experience -- restaurant browsing, menu viewing, cart management, order placement, and order tracking -- along with the critical location tracking capability that powers the dispatch engine. The app uses the device's GPS to detect when the customer enters geofence zones around restaurants, and it sends arrival events (5_MIN_OUT, PARKING, AT_DOOR, EXIT_VICINITY) to the backend to trigger order dispatch and auto-completion.

### Authentication and Authorization

Arrive uses a dual-authentication model. Customer and admin users authenticate through AWS Cognito, receiving JWT tokens that are validated by API Gateway authorizers on every request. The platform supports three user roles: "customer" for end users placing orders, "restaurant_admin" for managers of a specific restaurant, and "admin" for super administrators with platform-wide access. Role and restaurant assignment are stored as custom Cognito attributes and propagated through JWT claims.

POS systems use a separate authentication path. Each POS connection is issued an API key that is transmitted in the X-POS-API-Key request header. The key is hashed with SHA-256 before storage and lookup, ensuring that even a database breach does not expose usable credentials. Each key is scoped to a specific restaurant and carries an explicit list of permissions (such as "orders:write," "orders:read," "menu:read," "menu:write") following a fail-closed model where unset permissions default to denied.

### Geofencing Infrastructure

Arrive uses AWS Location Service to manage geofence zones around each restaurant. Three concentric zones are defined per restaurant location, corresponding to the three arrival events. These zones are managed through a geofence collection, and entry events are delivered to the Orders Service via EventBridge.

The geofencing system currently operates in shadow mode by default. In shadow mode, geofence events are received, logged, and recorded against orders, but they do not trigger actual dispatch transitions. This allows the platform to validate geofence accuracy and tune zone radii before enabling live cutover. The cutover is controlled by environment variables (LOCATION_GEOFENCE_CUTOVER_ENABLED and LOCATION_GEOFENCE_FORCE_SHADOW), making it possible to enable or disable live geofencing per deployment without code changes.


## Technical Maturity

Arrive is not a prototype or a proof of concept. It is a production-grade platform that has undergone a comprehensive 14-phase code review covering every service, every frontend, every test, every script, and every infrastructure template in the repository. This review identified and resolved 70 distinct issues across security, correctness, performance, and reliability categories.

The platform includes 467 automated tests spanning unit tests for all backend services, integration tests for API endpoints, frontend component tests, end-to-end lifecycle tests, and infrastructure validation tests. A continuous integration pipeline runs on every push, executing linting (ruff for Python), security scanning (detect-secrets for credential detection), and the full test suite.

Security hardening measures include SHA-256 hashing of POS API keys at rest, scoped IAM policies that avoid resource wildcards, S3 bucket policies that block public access, CORS origin validation derived from environment variables rather than hardcoded values, API Gateway throttling on the POS integration service (burst limit of 100 requests, sustained rate of 50 requests per second), and Cognito email validation to prevent filter injection attacks.


## Current State and Honest Assessment

Arrive is a functional, deployable platform with real capabilities. The following is a candid assessment of what is built and working today versus what remains aspirational.

### What Is Real

All four backend services are implemented, tested, and deployable via SAM/CloudFormation. The order lifecycle works end-to-end, from placement through dispatch, preparation, and completion. The capacity gating system correctly limits concurrent orders per restaurant per time window. The dispatch engine processes arrival events and transitions order states accordingly. Menu management supports full CRUD with CSV/Excel import. The Admin Portal provides a functional Kanban board with real-time polling, audio notifications, and auto-promotion. POS integration supports order creation, status updates, menu sync, and webhook ingestion with proper authentication and idempotency. All three frontends are functional and communicate with the backend APIs.

### What Is Partially Built

Geofencing is fully implemented in code but operates in shadow mode by default. The infrastructure for geofence zones is deployed (AWS Location Service collections, EventBridge rules), and the event processing pipeline works, but live dispatch cutover has not been enabled in production. The mobile app sends location updates, and the backend processes them, but the geofence-triggered dispatch path requires a configuration flag to be flipped.

Google OAuth sign-in parameters exist in the Cognito configuration, but the identity provider has not been provisioned. Customers currently authenticate with email and password only.

### What Is Aspirational

The payment model is PAY_AT_RESTAURANT. There is no online payment processing, no credit card integration, and no in-app checkout. The platform calculates an Arrive platform fee (2% of order total, split between restaurant and customer) and records it on each order, but this fee is informational only and is not collected through any payment processor.

Push notifications for order status updates are not yet implemented. The mobile app polls the backend for order status rather than receiving real-time push notifications.

There is no analytics dashboard for restaurant insights, no multi-location chain management, and no adaptive capacity learning from historical patterns.


## Key Differentiator

What sets Arrive apart from conventional ordering platforms is the location-aware dispatch engine. Most restaurant ordering systems follow a simple model: customer orders, restaurant cooks immediately, food sits and waits. The timing is left to chance. Arrive introduces a fundamentally different model: the platform holds the order, tracks the customer's approach in real time, and dispatches to the kitchen at the optimal moment so the food is ready exactly when the customer walks in.

This is not a minor feature layered onto an existing ordering system. It is the architectural foundation of the entire platform. The order state machine, the capacity gating system, the geofence infrastructure, the mobile location tracking, the progressive arrival events -- all of these are purpose-built to solve the timing problem. Every design decision in the system flows from the premise that the right time to start cooking is not when the order is placed, but when the customer is approaching.

For restaurants, this means less food waste, more consistent quality, and better kitchen throughput. For customers, it means fresh food, no waiting, and a dine-in experience that feels effortless -- they walk in, sit down, and their meal arrives at the table. For the platform, it means a genuine technical moat -- the coordination engine is complex to build, difficult to replicate, and gets better as geofence data improves over time.


## Deployment Model

Arrive runs entirely on AWS serverless infrastructure. The deployment is defined in a root SAM template (template.yaml) that orchestrates nested CloudFormation stacks for each service. Lambda functions run on Python 3.11 with a shared layer providing common utilities (authentication, CORS handling, structured logging, JSON serialization). Frontend applications are built with Vite and deployed to S3 buckets behind CloudFront distributions.

The serverless model means there are no servers to manage, no capacity planning for compute resources, and costs scale linearly with usage. A restaurant with ten orders per day and a restaurant with ten thousand orders per day run on the same infrastructure -- Lambda scales automatically, DynamoDB handles the throughput, and API Gateway manages the traffic.

Infrastructure is defined as code, fully reproducible, and deployable to any AWS region. The CI pipeline validates the infrastructure templates alongside the application code, catching configuration errors before deployment.


## Summary

Arrive is a restaurant ordering platform that uses real-time geofencing to coordinate food preparation with customer arrival. Customers order ahead, and the platform tracks their approach to dispatch orders to the kitchen at exactly the right moment -- so when the customer walks in, sits down, and identifies themselves, their food is freshly prepared and served to the table. It runs on a production-grade AWS serverless stack with four backend services, three frontend applications, comprehensive test coverage, and security hardening born from a rigorous 14-phase code review. The platform's location-aware dispatch engine is its core innovation, transforming the dine-in experience by turning the customer's travel time into the kitchen's prep time.

The system is built, tested, and deployable today. Geofencing operates in shadow mode pending production cutover. Payment is handled at the restaurant. The foundation is solid, the architecture is sound, and the platform is ready for its next phase of development and deployment.
