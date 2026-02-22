# POS Integration Contract (Current Implementation)

Last updated: 2026-02-21

## What Exists Today
The implemented POS surface is an API-key authenticated integration service (`services/pos-integration`).

Auth model:
- Header: `X-POS-API-Key`
- Backed by `PosApiKeysTable`
- Permission checks (`orders:read`, `orders:write`, `menu:read`, `menu:write`)

## Implemented Endpoints
- `POST /v1/pos/orders`
- `GET /v1/pos/orders`
- `POST /v1/pos/orders/{order_id}/status`
- `POST /v1/pos/orders/{order_id}/fire`
- `GET /v1/pos/menu`
- `POST /v1/pos/menu/sync` (feature-gated by `POS_MENU_SYNC_ENABLED`)
- `POST /v1/pos/webhook`

## Webhook Behavior
`POST /v1/pos/webhook` supports generic inbound POS events with idempotency:
- dedupe key: `webhook_id` (or `event_id`, fallback generated)
- logs events in `PosWebhookLogsTable` with TTL
- routes event types:
  - `order.created` / `order.placed` -> create order
  - `order.updated` / `order.status_changed` -> update status
  - unknown event -> acknowledged (no-op)

## Restaurant POS Configuration Source
Restaurant-level POS settings are managed in restaurants config (`/v1/restaurants/{restaurant_id}/config`):
- `pos_enabled`
- `pos_connections[]` with:
  - `connection_id`
  - `provider` (`square`, `toast`, `clover`, `custom`)
  - `webhook_url` (HTTPS required)
  - `webhook_secret` (masked in read responses)
  - `enabled`

## Deployment Note
The POS service template exists, but default `infrastructure/template.yaml` does not currently nest/deploy it. Treat this as a standalone deployment target until integrated.
