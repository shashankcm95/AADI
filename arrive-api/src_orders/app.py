import json
import os
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone

from core.models import (
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_WAITING,
    STATUS_EXPIRED,
    RECEIPT_SOFT,
    RECEIPT_HARD,
)
from core.engine import decide_vicinity_update, decide_ack_upgrade

from adapters.orders_repo_ddb import OrdersRepoDdb
from adapters.config_repo_ddb import ConfigRepoDdb
from adapters.capacity_repo_ddb import CapacityRepoDdb


# -------------------------
# Globals / Config
# -------------------------

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
RESTAURANT_CONFIG_TABLE = os.environ["RESTAURANT_CONFIG_TABLE"]
CAPACITY_TABLE = os.environ["CAPACITY_TABLE"]

orders_repo = OrdersRepoDdb(ORDERS_TABLE)
config_repo = ConfigRepoDdb(RESTAURANT_CONFIG_TABLE)
capacity_repo = CapacityRepoDdb(CAPACITY_TABLE)


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


def _log(event: str, **fields):
    payload = {"event": event, "ts": _now()}
    payload.update(fields)
    print(json.dumps(payload, default=_json_default))


def _parse_json(body: str) -> dict:
    try:
        return json.loads(body or "{}")
    except json.JSONDecodeError:
        return {}


# -------------------------
# Lambda Router
# -------------------------

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path") or ""
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    qs = event.get("queryStringParameters") or {}
    body = event.get("body") or "{}"

    if method == "POST" and path == "/v1/orders":
        return create_order(_parse_json(body))

    if method == "POST" and path.startswith("/v1/orders/") and path.endswith("/vicinity"):
        return update_vicinity(path.split("/")[3], _parse_json(body))

    if (
        method == "POST"
        and path.startswith("/v1/restaurants/")
        and "/orders/" in path
        and path.endswith("/ack")
    ):
        parts = path.split("/")
        return restaurant_ack_order(parts[3], parts[5], _parse_json(body))

    if method == "GET" and path.startswith("/v1/restaurants/") and path.endswith("/orders"):
        return list_restaurant_orders(path.split("/")[3], qs.get("status") or STATUS_SENT)

    return _resp(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})


# -------------------------
# Order Create
# -------------------------

def create_order(payload: dict):
    restaurant_id = payload.get("restaurant_id")
    items = payload.get("items")

    if not restaurant_id or not isinstance(items, list) or len(items) == 0:
        return _resp(400, {"error": {"code": "VALIDATION"}})

    now = _now()
    order_id = f"ord_{uuid.uuid4().hex[:16]}"

    total = 0
    units = 0
    norm_items = []

    for it in items:
        if not isinstance(it, dict) or "id" not in it:
            return _resp(400, {"error": {"code": "VALIDATION"}})

        qty = int(it.get("qty", 1))
        price = int(it.get("price_cents", 0))
        prep = int(it.get("prep_units", 1))

        total += price * qty
        units += prep * qty

        norm_items.append(
            {
                "id": it["id"],
                "qty": qty,
                "name": it.get("name"),
                "price_cents": price,
                "prep_units": prep,
            }
        )

    orders_repo.put_order(
        {
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
        }
    )

    _log(
        "ORDER_CREATED",
        order_id=order_id,
        restaurant_id=restaurant_id,
        prep_units_total=units,
        total_cents=total,
        expires_at=now + 1800,
    )

    return _resp(
        201,
        {
            "order_id": order_id,
            "status": STATUS_PENDING,
            "expires_at": now + 1800,
        },
    )


# -------------------------
# Vicinity → Send (capacity-gated)
# -------------------------

def update_vicinity(order_id: str, payload: dict):
    vicinity = payload.get("vicinity")
    if vicinity is not True and vicinity is not False:
        return _resp(400, {"error": {"code": "VALIDATION", "message": "vicinity must be boolean"}})

    order = orders_repo.get_order(order_id)
    if not order:
        return _resp(404, {"error": {"code": "NOT_FOUND"}})

    _log(
        "VICINITY_UPDATE",
        order_id=order_id,
        restaurant_id=order.get("restaurant_id"),
        status=order.get("status"),
        vicinity=vicinity,
    )

    now = _now()

    # Expiry handling stays in adapter-layer for now (behavior unchanged)
    if now > int(order.get("expires_at", 0)):
        orders_repo.update_order(
            Key={"order_id": order_id},
            UpdateExpression="SET #s=:e",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":e": STATUS_EXPIRED},
        )
        _log("ORDER_EXPIRED", order_id=order_id, restaurant_id=order.get("restaurant_id"))
        return _resp(409, {"error": {"code": "EXPIRED"}})

    # Only attempt capacity reservation when it could lead to dispatch
    ws_sec, max_units = config_repo.get_capacity_config(order["restaurant_id"])
    ws = _window_start(now, ws_sec)

    reserved = False
    if vicinity is True and order.get("status") in (STATUS_PENDING, STATUS_WAITING):
        _log(
            "CAPACITY_CHECK",
            order_id=order_id,
            restaurant_id=order.get("restaurant_id"),
            window_start=ws,
            window_seconds=ws_sec,
            add_units=order.get("prep_units_total"),
            max_units=max_units,
        )
        reserved = capacity_repo.try_reserve_capacity(
            order["restaurant_id"],
            ws,
            int(order.get("prep_units_total", 0)),
            max_units,
        )

    plan = decide_vicinity_update(
        order=order,
        vicinity=vicinity,
        now=now,
        window_seconds=ws_sec,
        max_units=max_units,
        window_start=ws,
        reserved_capacity=reserved,
    )

    # Apply plan updates (if any)
    if plan.set_fields or plan.remove_fields:
        update_expr_parts = []
        expr_names = {"#s": "status"} if "status" in (plan.set_fields or {}) else {}
        expr_values = {}

        # SET ...
        if plan.set_fields:
            set_chunks = []
            for k, v in plan.set_fields.items():
                if k == "status":
                    set_chunks.append("#s = :status")
                    expr_values[":status"] = v
                else:
                    placeholder = f":{k}"
                    set_chunks.append(f"{k} = {placeholder}")
                    expr_values[placeholder] = v
            update_expr_parts.append("SET " + ", ".join(set_chunks))

        # REMOVE ...
        if plan.remove_fields:
            update_expr_parts.append("REMOVE " + ", ".join(plan.remove_fields))

        kwargs = {
            "Key": {"order_id": order_id},
            "UpdateExpression": " ".join(update_expr_parts),
            "ExpressionAttributeValues": expr_values,
        }
        if expr_names:
            kwargs["ExpressionAttributeNames"] = expr_names

        # Optional condition (idempotency / state safety)
        if plan.condition_allowed_statuses:
            cond_vals = {}
            cond_list = []
            for i, s in enumerate(plan.condition_allowed_statuses):
                ph = f":c{i}"
                cond_vals[ph] = s
                cond_list.append(ph)
            kwargs["ConditionExpression"] = f"#s IN ({', '.join(cond_list)})"
            kwargs["ExpressionAttributeNames"] = {**kwargs.get("ExpressionAttributeNames", {}), "#s": "status"}
            kwargs["ExpressionAttributeValues"] = {**kwargs["ExpressionAttributeValues"], **cond_vals}

        try:
            orders_repo.update_order(**kwargs)
        except Exception:
            # keep behavior: best-effort; caller gets current status
            latest = orders_repo.get_order(order_id) or order
            return _resp(200, {"order_id": order_id, "status": latest.get("status")})

    # Emit lifecycle logs in the same places as before
    if plan.response and plan.response.get("status") == STATUS_SENT and order.get("status") in (STATUS_PENDING, STATUS_WAITING):
        _log(
            "ORDER_DISPATCHED",
            order_id=order_id,
            restaurant_id=order.get("restaurant_id"),
            from_status=order.get("status"),
            to_status=STATUS_SENT,
            sent_at=now,
            window_start=ws,
            receipt_mode=RECEIPT_SOFT,
        )

    if plan.response and plan.response.get("status") == STATUS_WAITING and order.get("status") in (STATUS_PENDING, STATUS_WAITING):
        suggested = plan.response.get("suggested_start_at") or (ws + ws_sec)
        _log(
            "CAPACITY_BLOCKED",
            order_id=order_id,
            restaurant_id=order.get("restaurant_id"),
            from_status=order.get("status"),
            to_status=STATUS_WAITING,
            suggested_start_at=suggested,
        )

    # Ensure ISO is included for WAITING (keep response consistent)
    if plan.response and plan.response.get("status") == STATUS_WAITING:
        ssa = plan.response.get("suggested_start_at")
        return _resp(
            200,
            {
                "order_id": order_id,
                "status": STATUS_WAITING,
                "suggested_start_at": ssa,
                "suggested_start_at_iso": _iso_utc(ssa),
            },
        )

    return _resp(200, plan.response or {"order_id": order_id, "status": order.get("status")})


# -------------------------
# Restaurant ACK (Hard)
# -------------------------

def restaurant_ack_order(restaurant_id: str, order_id: str, payload: dict):
    order = orders_repo.get_order(order_id)
    if not order or order.get("restaurant_id") != restaurant_id:
        return _resp(404, {"error": {"code": "NOT_FOUND"}})

    _log(
        "RESTAURANT_ACK_REQUEST",
        order_id=order_id,
        restaurant_id=restaurant_id,
        status=order.get("status"),
        current_receipt_mode=order.get("receipt_mode"),
    )

    now = _now()

    # Pure decision logic
    plan = decide_ack_upgrade(order=order, restaurant_id=restaurant_id, now=now)

    # Apply plan if any state change
    if plan.set_fields:
        expr_names = {"#s": "status"} if "status" in plan.set_fields else {"#s": "status"}
        expr_values = {}
        set_chunks = []

        for k, v in plan.set_fields.items():
            ph = f":{k}"
            set_chunks.append(f"{k} = {ph}")
            expr_values[ph] = v

        kwargs = {
            "Key": {"order_id": order_id},
            "UpdateExpression": "SET " + ", ".join(set_chunks),
            "ExpressionAttributeValues": expr_values,
        }

        # Condition: ensure still SENT
        kwargs["ConditionExpression"] = "#s = :sent"
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"][":sent"] = STATUS_SENT

        try:
            orders_repo.update_order(**kwargs)
            _log(
                "RESTAURANT_ACK_UPGRADED",
                order_id=order_id,
                restaurant_id=restaurant_id,
                receipt_mode=RECEIPT_HARD,
                received_at=now,
            )
        except Exception:
            # idempotent / race
            latest = orders_repo.get_order(order_id) or order
            if latest.get("receipt_mode") == RECEIPT_HARD:
                _log("RESTAURANT_ACK_IDEMPOTENT", order_id=order_id, restaurant_id=restaurant_id)
                return _resp(200, {"order_id": order_id, "receipt_mode": RECEIPT_HARD})
            return _resp(409, {"error": {"code": "INVALID_STATE"}})

    else:
        # Already HARD
        _log("RESTAURANT_ACK_IDEMPOTENT", order_id=order_id, restaurant_id=restaurant_id)

    return _resp(200, plan.response or {"order_id": order_id, "receipt_mode": RECEIPT_HARD})


# -------------------------
# List Orders
# -------------------------

def list_restaurant_orders(restaurant_id: str, status: str):
    items = orders_repo.query_by_restaurant_status(restaurant_id, status)
    items.sort(key=lambda x: x.get("sent_at", x.get("created_at", 0)))
    return _resp(200, {"restaurant_id": restaurant_id, "status": status, "orders": items})
