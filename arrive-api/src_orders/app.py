import json
import os
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

# -------------------------
# Globals / Config
# -------------------------

ddb = boto3.resource("dynamodb")

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
RESTAURANT_CONFIG_TABLE = os.environ["RESTAURANT_CONFIG_TABLE"]
CAPACITY_TABLE = os.environ["CAPACITY_TABLE"]

STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_RESTAURANT"
STATUS_WAITING = "WAITING_FOR_CAPACITY"
STATUS_EXPIRED = "EXPIRED"

RECEIPT_SOFT = "SOFT"
RECEIPT_HARD = "HARD"


# -------------------------
# Helpers
# -------------------------

def _now() -> int:
    return int(time.time())

def _iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()

def _window_start(now: int, window_seconds: int) -> int:
    return now - (now % window_seconds)

def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    return str(o)

def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


# -------------------------
# Capacity
# -------------------------

def _get_capacity_config(restaurant_id: str) -> tuple[int, int]:
    cfg = ddb.Table(RESTAURANT_CONFIG_TABLE)
    item = cfg.get_item(Key={"restaurant_id": restaurant_id}).get("Item") or {}
    return (
        int(item.get("capacity_window_seconds", 600)),
        int(item.get("max_prep_units_per_window", 20)),
    )

def _try_reserve_capacity(
    restaurant_id: str,
    window_start: int,
    add_units: int,
    max_units: int,
) -> bool:
    cap = ddb.Table(CAPACITY_TABLE)
    ttl = window_start + 6 * 3600

    try:
        cap.update_item(
            Key={"restaurant_id": restaurant_id, "window_start": window_start},
            UpdateExpression="SET #ttl = :ttl ADD used_units :add",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ConditionExpression=(
                "(attribute_not_exists(used_units) AND :add <= :max) "
                "OR (used_units <= :limit)"
            ),
            ExpressionAttributeValues={
                ":add": add_units,
                ":max": max_units,
                ":limit": max_units - add_units,
                ":ttl": ttl,
            },
        )
        return True
    except Exception as e:
        print(f"CAPACITY_RESERVE_ERROR: {type(e).__name__}: {e}")
        return False


# -------------------------
# Lambda Router
# -------------------------

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path") or ""
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    qs = event.get("queryStringParameters") or {}
    body = event.get("body") or "{}"

    if method == "POST" and path == "/v1/orders":
        return create_order(json.loads(body))

    if method == "POST" and path.startswith("/v1/orders/") and path.endswith("/vicinity"):
        return update_vicinity(path.split("/")[3], json.loads(body))

    if (
        method == "POST"
        and path.startswith("/v1/restaurants/")
        and "/orders/" in path
        and path.endswith("/ack")
    ):
        parts = path.split("/")
        return restaurant_ack_order(parts[3], parts[5], json.loads(body or "{}"))

    if method == "GET" and path.startswith("/v1/restaurants/") and path.endswith("/orders"):
        return list_restaurant_orders(path.split("/")[3], qs.get("status") or STATUS_SENT)

    return _resp(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})


# -------------------------
# Order Create
# -------------------------

def create_order(payload: dict):
    restaurant_id = payload.get("restaurant_id")
    items = payload.get("items")

    if not restaurant_id or not items:
        return _resp(400, {"error": {"code": "VALIDATION"}})

    now = _now()
    order_id = f"ord_{uuid.uuid4().hex[:16]}"

    total = 0
    units = 0
    norm_items = []

    for it in items:
        qty = int(it.get("qty", 1))
        price = int(it.get("price_cents", 0))
        prep = int(it.get("prep_units", 1))
        total += price * qty
        units += prep * qty
        norm_items.append({
            "id": it["id"],
            "qty": qty,
            "name": it.get("name"),
            "price_cents": price,
            "prep_units": prep,
        })

    ddb.Table(ORDERS_TABLE).put_item(Item={
        "order_id": order_id,
        "restaurant_id": restaurant_id,
        "status": STATUS_PENDING,
        "created_at": now,
        "expires_at": now + 1800,
        "customer_name": payload.get("customer_name", "Guest"),
        "items": norm_items,
        "total_cents": total,
        "prep_units_total": units,
        "vicinity": False,
    })

    return _resp(201, {
        "order_id": order_id,
        "status": STATUS_PENDING,
        "expires_at": now + 1800,
    })


# -------------------------
# Vicinity → Send
# -------------------------

def update_vicinity(order_id: str, payload: dict):
    vicinity = payload.get("vicinity")
    table = ddb.Table(ORDERS_TABLE)

    order = table.get_item(Key={"order_id": order_id}).get("Item")
    if not order:
        return _resp(404, {"error": {"code": "NOT_FOUND"}})

    now = _now()
    if now > order["expires_at"]:
        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s=:e",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":e": STATUS_EXPIRED},
        )
        return _resp(409, {"error": {"code": "EXPIRED"}})

    if vicinity is True and order["status"] in (STATUS_PENDING, STATUS_WAITING):
        ws_sec, max_units = _get_capacity_config(order["restaurant_id"])
        ws = _window_start(now, ws_sec)

        if _try_reserve_capacity(order["restaurant_id"], ws, order["prep_units_total"], max_units):
            table.update_item(
                Key={"order_id": order_id},
                ConditionExpression="#s IN (:p, :w)",
                UpdateExpression=(
                    "SET #s=:sent, vicinity=:v, sent_at=:t, "
                    "capacity_window_start=:ws, "
                    "received_by_restaurant=:r, received_at=:t, receipt_mode=:soft "
                    "REMOVE waiting_since, suggested_start_at"
                ),
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":p": STATUS_PENDING,
                    ":w": STATUS_WAITING,
                    ":sent": STATUS_SENT,
                    ":v": True,
                    ":t": now,
                    ":ws": ws,
                    ":r": True,
                    ":soft": RECEIPT_SOFT,
                },
            )
            return _resp(200, {"order_id": order_id, "status": STATUS_SENT})

        table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s=:w, vicinity=:v, waiting_since=:t, suggested_start_at=:ssa",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":w": STATUS_WAITING,
                ":v": True,
                ":t": now,
                ":ssa": ws + ws_sec,
            },
        )

        # Capacity full
        return _resp(200, {
            "order_id": order_id,
            "status": STATUS_WAITING,
            "suggested_start_at": ws + ws_sec,
            "suggested_start_at_iso": _iso_utc(ws + ws_sec),
        })

    return _resp(200, {"order_id": order_id, "status": order["status"]})


# -------------------------
# Restaurant ACK (Hard)
# -------------------------

def restaurant_ack_order(restaurant_id: str, order_id: str, payload: dict):
    table = ddb.Table(ORDERS_TABLE)
    order = table.get_item(Key={"order_id": order_id}).get("Item")

    if not order or order["restaurant_id"] != restaurant_id:
        return _resp(404, {"error": {"code": "NOT_FOUND"}})

    if order["status"] != STATUS_SENT:
        return _resp(409, {"error": {"code": "INVALID_STATE"}})

    if order.get("receipt_mode") == RECEIPT_HARD:
        return _resp(200, {"order_id": order_id, "receipt_mode": RECEIPT_HARD})

    now = _now()

    table.update_item(
        Key={"order_id": order_id},
        ConditionExpression="#s=:sent AND receipt_mode=:soft",
        UpdateExpression="SET receipt_mode=:hard, received_at=:t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":sent": STATUS_SENT,
            ":soft": RECEIPT_SOFT,
            ":hard": RECEIPT_HARD,
            ":t": now,
        },
    )

    return _resp(200, {
        "order_id": order_id,
        "receipt_mode": RECEIPT_HARD,
        "received_at": now,
    })


# -------------------------
# List Orders
# -------------------------

def list_restaurant_orders(restaurant_id: str, status: str):
    res = ddb.Table(ORDERS_TABLE).query(
        IndexName="GSI_RestaurantStatus",
        KeyConditionExpression=Key("restaurant_id").eq(restaurant_id) & Key("status").eq(status),
    )
    items = res.get("Items", [])
    items.sort(key=lambda x: x.get("sent_at", x.get("created_at", 0)))
    return _resp(200, {"restaurant_id": restaurant_id, "status": status, "orders": items})
