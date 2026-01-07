import json
import os
import time
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

ddb = boto3.resource("dynamodb")
ORDERS_TABLE = os.environ["ORDERS_TABLE"]

STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_RESTAURANT"
STATUS_EXPIRED = "EXPIRED"  # not used yet, but reserved


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
    If vicinity true and status PENDING_NOT_SENT and not expired => transition to SENT_TO_RESTAURANT.
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

    now = int(time.time())
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
    if vicinity is True and current_status == STATUS_PENDING:
        # Transition: PENDING -> SENT (idempotent-safe with condition)
        try:
            table.update_item(
                Key={"order_id": order_id},
                ConditionExpression="#s = :pending",
                UpdateExpression="SET #s = :sent, vicinity = :v, sent_at = :t",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":pending": STATUS_PENDING,
                    ":sent": STATUS_SENT,
                    ":v": True,
                    ":t": now,
                },
                ReturnValues="ALL_NEW",
            )
        except Exception:
            # If condition fails, treat as already sent or changed
            latest = table.get_item(Key={"order_id": order_id}).get("Item", {})
            return _resp(200, {"order_id": order_id, "status": latest.get("status"), "vicinity": latest.get("vicinity")})

        latest = table.get_item(Key={"order_id": order_id}).get("Item", {})
        return _resp(200, {"order_id": order_id, "status": latest.get("status"), "vicinity": latest.get("vicinity")})

    # For prototype: allow clearing vicinity but do not revert SENT
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

