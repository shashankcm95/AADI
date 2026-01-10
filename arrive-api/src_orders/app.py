import json
import os
import time
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone

ddb = boto3.resource("dynamodb")
ORDERS_TABLE = os.environ["ORDERS_TABLE"]

STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_RESTAURANT"
STATUS_EXPIRED = "EXPIRED"  # not used yet, but reserved
STATUS_WAITING = "WAITING_FOR_CAPACITY"

RESTAURANT_CONFIG_TABLE = os.environ["RESTAURANT_CONFIG_TABLE"]
CAPACITY_TABLE = os.environ["CAPACITY_TABLE"]

def _iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()

def _json_default(o):
    if isinstance(o, Decimal):
        if o % 1 == 0:
            return int(o)
        return float(o)
    return str(o)


def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }

def _now() -> int:
    return int(time.time())

def _window_start(now: int, window_seconds: int) -> int:
    return now - (now % window_seconds)

def _get_capacity_config(restaurant_id: str) -> tuple[int, int]:
    cfg_table = ddb.Table(RESTAURANT_CONFIG_TABLE)
    item = cfg_table.get_item(Key={"restaurant_id": restaurant_id}).get("Item") or {}
    window_seconds = int(item.get("capacity_window_seconds", 600))
    max_units = int(item.get("max_prep_units_per_window", 20))
    return window_seconds, max_units

def _try_reserve_capacity(restaurant_id: str, window_start: int, add_units: int, max_units: int) -> bool:
    """
    Atomically reserve capacity for a restaurant window.
    Condition ensures used_units + add_units <= max_units.
    """
    cap_table = ddb.Table(CAPACITY_TABLE)
    ttl = window_start + 6 * 3600  # keep 6 hours then auto-expire

    try:
        cap_table.update_item(
            Key={"restaurant_id": restaurant_id, "window_start": window_start},
            UpdateExpression="SET #ttl = :ttl ADD used_units :add",
            ExpressionAttributeNames={
                "#ttl": "ttl",
            },
            ConditionExpression="(attribute_not_exists(used_units) AND :add <= :max) OR (used_units <= :limit)",
            ExpressionAttributeValues={
                ":add": add_units,
                ":max": max_units,
                ":limit": max_units - add_units,
                ":ttl": ttl,
            },
        )

        return True
    except Exception as e:
        # Keep this lightweight; DynamoDB failures should not crash the request.
        print(f"CAPACITY_RESERVE_ERROR: {type(e).__name__}: {e}")
        return False


def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path") or ""
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    qs = event.get("queryStringParameters") or {}
    body = event.get("body") or "{}"

    # Route: POST /v1/orders
    if method == "POST" and path == "/v1/orders":
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        return create_order(payload)

    # Route: POST /v1/orders/{order_id}/vicinity
    if method == "POST" and path.startswith("/v1/orders/") and path.endswith("/vicinity"):
        parts = path.split("/")
        # ["", "v1", "orders", "{order_id}", "vicinity"]
        if len(parts) >= 5:
            order_id = parts[3]
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
            return update_vicinity(order_id, payload)
        
    # Route: GET /v1/restaurants/{restaurant_id}/orders?status=...
    if method == "GET" and path.startswith("/v1/restaurants/") and path.endswith("/orders"):
        parts = path.split("/")
        # ["", "v1", "restaurants", "{restaurant_id}", "orders"]
        if len(parts) >= 5:
            restaurant_id = parts[3]
            status = qs.get("status") or STATUS_SENT
            return list_restaurant_orders(restaurant_id, status)

    return _resp(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})


def create_order(payload: dict):
    """
    Minimal order create.
    Expected:
      restaurant_id: str
      items: [{ id, qty, name?, price_cents?, prep_units? }]
      customer_name: optional
    """
    restaurant_id = payload.get("restaurant_id")
    items = payload.get("items")

    if not restaurant_id or not isinstance(restaurant_id, str):
        return _resp(400, {"error": {"code": "VALIDATION", "message": "restaurant_id is required"}})
    if not items or not isinstance(items, list):
        return _resp(400, {"error": {"code": "VALIDATION", "message": "items must be a non-empty list"}})

    now = int(time.time())
    order_id = f"ord_{uuid.uuid4().hex[:16]}"
    expires_at = now + 30 * 60  # 30 min prototype rule

    # Prototype: compute totals if present; otherwise default
    total_cents = 0
    prep_units_total = 0
    norm_items = []
    for it in items:
        if not isinstance(it, dict) or "id" not in it:
            return _resp(400, {"error": {"code": "VALIDATION", "message": "each item must include id"}})
        qty = int(it.get("qty", 1))
        price_cents = int(it.get("price_cents", 0))
        prep_units = int(it.get("prep_units", 1))
        total_cents += price_cents * qty
        prep_units_total += prep_units * qty
        norm_items.append({
            "id": it["id"],
            "qty": qty,
            "name": it.get("name"),
            "price_cents": price_cents,
            "prep_units": prep_units,
        })

    table = ddb.Table(ORDERS_TABLE)
    item = {
        "order_id": order_id,
        "restaurant_id": restaurant_id,
        "status": STATUS_PENDING,
        "created_at": now,
        "expires_at": expires_at,
        "customer_name": payload.get("customer_name", "Guest"),
        "items": norm_items,
        "total_cents": total_cents,
        "prep_units_total": prep_units_total,
        "vicinity": False,
    }

    table.put_item(Item=item)

    return _resp(201, {
        "order_id": order_id,
        "status": item["status"],
        "expires_at": expires_at,
    })

def update_vicinity(order_id: str, payload: dict):
    """
    Body:
      { "vicinity": true }
    If vicinity true and status PENDING_NOT_SENT and not expired => either:
      - reserve capacity and transition to SENT_TO_RESTAURANT
      - or transition to WAITING_FOR_CAPACITY with suggested_start_at
    """
    vicinity = payload.get("vicinity")
    if vicinity is not True and vicinity is not False:
        return _resp(400, {"error": {"code": "VALIDATION", "message": "vicinity must be boolean"}})

    table = ddb.Table(ORDERS_TABLE)

    # Load order
    res = table.get_item(Key={"order_id": order_id})
    order = res.get("Item")
    if not order:
        return _resp(404, {"error": {"code": "NOT_FOUND", "message": "order not found"}})

    now = _now()
    if now > int(order.get("expires_at", 0)):
        # Mark expired (best-effort)
        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s = :s, vicinity = :v",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": STATUS_EXPIRED, ":v": False},
        )
        return _resp(409, {"error": {"code": "EXPIRED", "message": "order expired"}})

    current_status = order.get("status")

    # Fire (capacity-gated)
    if vicinity is True and current_status == STATUS_PENDING:
        restaurant_id = order["restaurant_id"]
        prep_units_total = int(order.get("prep_units_total", 1))

        window_seconds, max_units = _get_capacity_config(restaurant_id)
        ws = _window_start(now, window_seconds)

        reserved = _try_reserve_capacity(restaurant_id, ws, prep_units_total, max_units)

        if reserved:
            # Transition: PENDING -> SENT
            try:
                table.update_item(
                    Key={"order_id": order_id},
                    ConditionExpression="#s = :pending",
                    UpdateExpression=(
                        "SET #s = :sent, vicinity = :v, sent_at = :t, "
                        "capacity_window_start = :ws, received_by_restaurant = :r, received_at = :t"
                    ),
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":pending": STATUS_PENDING,
                        ":sent": STATUS_SENT,
                        ":v": True,
                        ":t": now,
                        ":ws": ws,
                        ":r": True,
                    },
                )
            except Exception:
                latest = table.get_item(Key={"order_id": order_id}).get("Item", {})
                return _resp(200, {
                    "order_id": order_id,
                    "status": latest.get("status"),
                    "vicinity": latest.get("vicinity"),
                })

            latest = table.get_item(Key={"order_id": order_id}).get("Item", {})
            return _resp(200, {
                "order_id": order_id,
                "status": latest.get("status"),
                "vicinity": latest.get("vicinity"),
            })

        # No capacity: move to WAITING_FOR_CAPACITY
        suggested_start_at = ws + window_seconds  # next window (v0)
        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s = :w, vicinity = :v, waiting_since = :t, suggested_start_at = :ssa",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":w": STATUS_WAITING,
                ":v": True,
                ":t": now,
                ":ssa": suggested_start_at,
            },
        )
        retry_after_seconds = max(0, int(suggested_start_at) - now)

        return _resp(200, {
            "order_id": order_id,
            "status": STATUS_WAITING,
            "vicinity": True,
            "suggested_start_at": suggested_start_at,
            "suggested_start_at_iso": _iso_utc(suggested_start_at),
            "retry_after_seconds": retry_after_seconds,
            "message": "Restaurant is at capacity. Start later to avoid waiting."
        })


    # Allow clearing vicinity but do not revert SENT
    if vicinity is False:
        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET vicinity = :v",
            ExpressionAttributeValues={":v": False},
        )
        latest = table.get_item(Key={"order_id": order_id}).get("Item", {})
        return _resp(200, {"order_id": order_id, "status": latest.get("status"), "vicinity": latest.get("vicinity")})

    return _resp(200, {"order_id": order_id, "status": current_status, "vicinity": order.get("vicinity", False)})

def list_restaurant_orders(restaurant_id: str, status: str):
    table = ddb.Table(ORDERS_TABLE)

    # Query GSI: restaurant_id + status
    res = table.query(
        IndexName="GSI_RestaurantStatus",
        KeyConditionExpression=Key("restaurant_id").eq(restaurant_id) & Key("status").eq(status),
    )
    items = res.get("Items", [])

    # Sort by sent_at if present, otherwise created_at
    items.sort(key=lambda x: int(x.get("sent_at", x.get("created_at", 0))))

    return _resp(200, {"restaurant_id": restaurant_id, "status": status, "orders": items})

