# 01 - System Overview

Version: 3.0
Last updated: 2026-02-21

## Runtime Topology
The default infrastructure stack deploys three backend services behind API Gateway HTTP APIs:
- Users service
- Restaurants service
- Orders service

A separate POS integration service exists in `services/pos-integration` and can be deployed independently.

## High-Level Flow
```text
Customer Web / Mobile
  -> Restaurants API (catalog/menu/favorites/config reads)
  -> Orders API (create, advisory, arrival, status)
  -> Users API (profile/avatar)

Admin Portal
  -> Restaurants API (management)
  -> Orders API (restaurant order progression)
```

## Mobile Geofencing Pipeline
- Mobile app starts background tracking after order placement when location permission and coordinates are available.
- Hybrid geofencing logic emits `5_MIN_OUT`, `PARKING`, and `AT_DOOR` events.
- Raw location samples are sent to `POST /v1/orders/{order_id}/location`.
- Orders service forwards location samples to Amazon Location Tracker.
- Geofence ENTER events from EventBridge are consumed by orders geofence handler (shadow mode by default).
- Arrival events are sent to `POST /v1/orders/{order_id}/vicinity` (manual/mobile primary path today).
- Orders service uses those events as dispatch triggers with capacity gating.
- Manual `"I'm Here"` action remains a fallback trigger.

## Auth Model
- Users/Restaurants/Orders: Cognito JWT authorizer
- POS integration: API key (`X-POS-API-Key`)

## Core Domain Concepts
- Session/order lifecycle status
- Arrival events as dispatch intent
- Capacity windows as restaurant protection mechanism

## Key Operational Behavior
- Order is created immediately, but not dispatched immediately.
- Dispatch only occurs when arrival event is eligible and capacity check succeeds.
- Restaurant UI/actions drive in-kitchen progression after dispatch.
