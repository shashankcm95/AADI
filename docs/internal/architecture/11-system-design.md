# 11 - Detailed System Design

Version: 3.0
Last updated: 2026-02-21

## A. Architectural Layers
1. Client layer: web/mobile/admin frontends
2. API/auth layer: API Gateway + Cognito JWT (except POS API key surface)
3. Service layer: users/restaurants/orders (+ optional pos-integration)
4. Storage layer: DynamoDB tables, S3 buckets for media

## B. Orders Engine Design
- Stateless Lambda execution
- Persistent state in DynamoDB
- Decision flow:
  1. validate auth and ownership
  2. load order
  3. validate expiry
  4. if arrival event dispatch-eligible and order pending/waiting -> reserve capacity
  5. apply transition via conditional update

Supporting arrival inputs:
- Client arrival endpoint (`/vicinity`) remains primary dispatch trigger path.
- Location ingest endpoint (`/location`) stores telemetry and forwards positions to Amazon Location tracker.
- EventBridge geofence handler records shadow comparisons and can be toggled to dispatch path via env flag.

## C. Restaurants Service Design
- Role-aware listing and management logic
- Menu stored as versioned document (`latest`)
- Config object includes capacity and POS connection fields
- Favorites relation table keyed by customer
- Presigned upload URLs for restaurant media assets

## D. Users Service Design
- Profile CRUD for authenticated user
- Presigned S3 upload URL for avatar update
- Post-confirmation trigger initializes role/profile baseline

## E. POS Service Design (Standalone)
- API-key auth with per-key permissions
- Format mappers for toast/square/generic payloads
- Webhook dedupe table to make webhook ingestion idempotent

## F. Reliability Characteristics
- Backend Python tests are strong and currently passing.
- Transition logic has explicit status-chain enforcement in orders engine.
- Capacity gating protects restaurant throughput under load.
- Geofence events are deduplicated with `GeofenceEventsTable` before processing.
