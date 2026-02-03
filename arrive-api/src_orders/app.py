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
from core.engine import decide_vicinity_update, decide_ack_upgrade, decide_cancel, decide_restaurant_status_update


from adapters.orders_repo_ddb import OrdersRepoDdb
from adapters.config_repo_ddb import ConfigRepoDdb
from adapters.capacity_repo_ddb import CapacityRepoDdb
from core.dynamo_apply import build_update_item_kwargs
from core.http_errors import map_core_error
from core.errors import ExpiredError, InvalidStateError, NotFoundError
import hashlib
from adapters.idempotency_repo_ddb import IdempotencyRepoDdb, IdempotencyConflictError

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

# -------------------------
# Cached dependency getter 
# -------------------------

from functools import lru_cache

_SER = TypeSerializer()

def _av(v):
    # TypeSerializer returns {"S": "..."} / {"N": "..."} / {"BOOL": True} / {"L": [...]} etc.
    return _SER.serialize(v)


@lru_cache(maxsize=1)
def _ddb():
    return boto3.client("dynamodb")


@lru_cache(maxsize=1)
def _deps():
    orders_table = os.getenv("ORDERS_TABLE")
    cfg_table = os.getenv("RESTAURANT_CONFIG_TABLE")
    cap_table = os.getenv("CAPACITY_TABLE")

    missing = [k for k, v in {
        "ORDERS_TABLE": orders_table,
        "RESTAURANT_CONFIG_TABLE": cfg_table,
        "CAPACITY_TABLE": cap_table,
    }.items() if not v]

    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    return (
        OrdersRepoDdb(orders_table),
        ConfigRepoDdb(cfg_table),
        CapacityRepoDdb(cap_table),
    )

@lru_cache(maxsize=1)
def _idemp_repo():
    table = os.getenv('IDEMPOTENCY_TABLE')
    if not table:
        return None
    return IdempotencyRepoDdb(table)
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

def _get_header(headers: dict, name: str) -> str | None:
    if not headers:
        return None
    lower=name.lower()
    for k,v in headers.items():
        if k and k.lower()==lower:
            return v
    return None

def _parse_json(body: str):
    try:
        return json.loads(body or "{}"), None
    except json.JSONDecodeError:
        return None, "BAD_JSON"


# -------------------------
# Lambda Router
# -------------------------

def lambda_handler(event, context):
    raw_path = event.get("rawPath") or event.get("path") or ""
    path = raw_path.rstrip("/") or "/"

    method = (
        event.get("requestContext", {})
            .get("http", {})
            .get("method")
        or event.get("httpMethod")
        or ""
    ).upper()

    qs = event.get("queryStringParameters") or {}
    body = event.get("body") or "{}"

    # POST /v1/orders
    if method == "POST" and path == "/v1/orders":
        payload, err = _parse_json(body)
        if err:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        idem_key = _get_header(event.get('headers') or {}, 'Idempotency-Key')
        return create_order(payload, idempotency_key=idem_key, raw_body=body)

    # POST /v1/orders/{order_id}/vicinity
    if method == "POST" and path.startswith("/v1/orders/") and path.endswith("/vicinity"):
        payload, err = _parse_json(body)
        if err:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        return update_vicinity(path.split("/")[3], payload)

    # POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack
    if (
        method == "POST"
        and path.startswith("/v1/restaurants/")
        and "/orders/" in path
        and path.endswith("/ack")
    ):
        parts = path.split("/")
        payload, err = _parse_json(body)
        if err:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        return restaurant_ack_order(parts[3], parts[5], payload)

    # GET /v1/restaurants/{restaurant_id}/orders?status=...
    if method == "GET" and path.startswith("/v1/restaurants/") and path.endswith("/orders"):
        return list_restaurant_orders(path.split("/")[3], qs.get("status") or STATUS_SENT)

    # Route: GET /v1/orders/{order_id}
    if method == "GET" and path.startswith("/v1/orders/") and len(path.split("/")) == 4:
        # ["", "v1", "orders", "{order_id}"]
        return get_order(path.split("/")[3])

    # POST /v1/orders/{order_id}/cancel
    if method == "POST" and path.startswith("/v1/orders/") and path.endswith("/cancel"):
        payload, err = _parse_json(body)
        if err:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        return cancel_order(path.split("/")[3])
    
    # POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status
    if (
        method == "POST"
        and path.startswith("/v1/restaurants/")
        and "/orders/" in path
        and path.endswith("/status")
    ):
        parts = path.split("/")
        payload, err = _parse_json(body)
        if err:
            return _resp(400, {"error": {"code": "BAD_JSON", "message": "Invalid JSON body"}})
        return restaurant_set_status(parts[3], parts[5], payload)


    return _resp(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})

# -------------------------
# Order Create
# -------------------------

def create_order(payload: dict, idempotency_key: str | None = None, raw_body: str | None = None):
    orders_repo, config_repo, capacity_repo = _deps()
    # Optional idempotency for POST /v1/orders
    idemp_repo = _idemp_repo()
    request_hash = None
    if idemp_repo and idempotency_key:
        existing = idemp_repo.get(idempotency_key)
        # Prefer raw_body (what the client actually sent) for stability
        material = (raw_body or json.dumps(payload, sort_keys=True, separators=(",", ":")))
        request_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
        if existing:
            try:
                idemp_repo.assert_same_request(existing, request_hash)
            except IdempotencyConflictError:
                return _resp(409, {"error": {"code": "IDEMPOTENCY_KEY_REUSED"}})
            # Return the stored response
            return {
                "statusCode": int(existing.get("response_status", 200)),
                "headers": {"Content-Type": "application/json"},
                "body": existing.get("response_body", "{}"),
            }

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

    resp = _resp(
        201,
        {
            "order_id": order_id,
            "status": STATUS_PENDING,
            "expires_at": now + 1800,
        },
    )
    # Best-effort write of idempotency record (after successful create)
    if idemp_repo and idempotency_key and request_hash:
        try:
            idemp_repo.put_response_if_absent(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status=int(resp["statusCode"]),
                response_body=resp["body"],
                created_at=now,
                ttl=now + 24 * 3600,
            )
        except Exception:
            # Ignore idempotency write failures for prototype; create succeeded.
            pass

    return resp

# -------------------------
# Vicinity → Send (capacity-gated)
# -------------------------

def update_vicinity(order_id: str, payload: dict):
    orders_repo, config_repo, capacity_repo = _deps()
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

    # Defaults only used when we don’t need config (vicinity=false or non-actionable state).
    ws_sec, max_units = 600, 20
    ws = _window_start(now, ws_sec)

    status = order.get("status")
    dispatched = False

    # Leak-free dispatch path:
    # If vicinity=true and status is actionable, attempt a single DynamoDB transaction:
    #   1) capacity reserve (conditional)
    #   2) order status update to SENT (conditional)
    if vicinity is True and status in (STATUS_PENDING, STATUS_WAITING):
        ws_sec, max_units = config_repo.get_capacity_config(order["restaurant_id"])
        ws = _window_start(now, ws_sec)

        add_units = int(order.get("prep_units_total", 0))
        _log(
            "CAPACITY_CHECK",
            order_id=order_id,
            restaurant_id=order.get("restaurant_id"),
            window_start=ws,
            window_seconds=ws_sec,
            add_units=add_units,
            max_units=max_units,
        )

        # Build the “dispatch” plan optimistically (reserved_capacity=True),
        # then attempt to apply it atomically with capacity reservation.
        try:
            plan = decide_vicinity_update(
                order=order,
                vicinity=vicinity,
                now=now,
                window_seconds=ws_sec,
                max_units=max_units,
                window_start=ws,
                reserved_capacity=True,
            )
        except (ExpiredError, InvalidStateError, NotFoundError) as e:
            spec = map_core_error(e)
            return _resp(spec.status_code, spec.body)

        # Only transact if the plan would actually dispatch.
        if plan.response and plan.response.get("status") == STATUS_SENT:
            orders_table = os.environ["ORDERS_TABLE"]
            capacity_table = os.environ["CAPACITY_TABLE"]

            ttl_seconds = 6 * 3600
            ttl = ws + ttl_seconds

            # Capacity Update (same condition as CapacityRepoDdb, but inside a transaction)
            cap_update = {
                "TableName": capacity_table,
                "Key": {
                    "restaurant_id": {"S": order["restaurant_id"]},
                    "window_start": {"N": str(ws)},
                },
                "UpdateExpression": "SET #ttl = :ttl ADD used_units :add",
                "ExpressionAttributeNames": {"#ttl": "ttl"},
                "ConditionExpression": (
                    "(attribute_not_exists(used_units) AND :add <= :max) "
                    "OR (used_units <= :limit)"
                ),
                "ExpressionAttributeValues": {
                    ":add": {"N": str(add_units)},
                    ":max": {"N": str(max_units)},
                    ":limit": {"N": str(max_units - add_units)},
                    ":ttl": {"N": str(ttl)},
                },
            }

            # Order Update (reuse your existing plan->Dynamo update builder, then serialize values)
            order_kwargs = build_update_item_kwargs(order_id, plan)
            if order_kwargs:
                order_update = {
                    "TableName": orders_table,
                    "Key": {"order_id": {"S": order_id}},
                    "UpdateExpression": order_kwargs["UpdateExpression"],
                }
                if "ConditionExpression" in order_kwargs:
                    order_update["ConditionExpression"] = order_kwargs["ConditionExpression"]
                if "ExpressionAttributeNames" in order_kwargs:
                    order_update["ExpressionAttributeNames"] = order_kwargs["ExpressionAttributeNames"]
                if "ExpressionAttributeValues" in order_kwargs:
                    order_update["ExpressionAttributeValues"] = {
                        k: _av(v) for k, v in order_kwargs["ExpressionAttributeValues"].items()
                    }

                try:
                    _ddb().transact_write_items(
                        TransactItems=[
                            {"Update": cap_update},
                            {"Update": order_update},
                        ]
                    )
                    dispatched = True
                except ClientError as e:
                    code = (e.response.get("Error") or {}).get("Code")
                    # Capacity full or stale status -> treat as “not reserved”, fall through to WAITING logic.
                    if code not in ("TransactionCanceledException", "ConditionalCheckFailedException"):
                        raise

    if not dispatched:
        # Non-dispatch path: keep existing behavior (WAITING / no-op responses).
        try:
            plan = decide_vicinity_update(
                order=order,
                vicinity=vicinity,
                now=now,
                window_seconds=ws_sec,
                max_units=max_units,
                window_start=ws,
                reserved_capacity=False,
            )
        except (ExpiredError, InvalidStateError, NotFoundError) as e:
            spec = map_core_error(e)
            return _resp(spec.status_code, spec.body)

        kwargs = build_update_item_kwargs(order_id, plan)
        if kwargs:
            try:
                orders_repo.update_order(**kwargs)
            except Exception:
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
    orders_repo, config_repo, capacity_repo = _deps()
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

    try:
        # Pure decision logic
        plan = decide_ack_upgrade(order=order, restaurant_id=restaurant_id, now=now)
    except (ExpiredError, InvalidStateError, NotFoundError) as e:
        spec = map_core_error(e)
        return _resp(spec.status_code, spec.body)

    # Apply plan if any state change
    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
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
            latest = orders_repo.get_order(order_id) or order
            if latest.get("receipt_mode") == RECEIPT_HARD:
                _log("RESTAURANT_ACK_IDEMPOTENT", order_id=order_id, restaurant_id=restaurant_id)
                return _resp(200, {"order_id": order_id, "receipt_mode": RECEIPT_HARD})
            return _resp(409, {"error": {"code": "INVALID_STATE"}})
    else:
        _log("RESTAURANT_ACK_IDEMPOTENT", order_id=order_id, restaurant_id=restaurant_id)

    return _resp(200, plan.response or {"order_id": order_id, "receipt_mode": RECEIPT_HARD})


def get_order(order_id: str):
    orders_repo, _, _ = _deps()
    order = orders_repo.get_order(order_id)
    if not order:
        return _resp(404, {"error": {"code": "NOT_FOUND", "message": "order not found"}})

    # Return a stable “public” view (you can add fields later safely)
    return _resp(200, {
        "order_id": order.get("order_id"),
        "restaurant_id": order.get("restaurant_id"),
        "status": order.get("status"),
        "receipt_mode": order.get("receipt_mode"),
        "created_at": order.get("created_at"),
        "sent_at": order.get("sent_at"),
        "expires_at": order.get("expires_at"),
        "waiting_since": order.get("waiting_since"),
        "suggested_start_at": order.get("suggested_start_at"),
        "items": order.get("items", []),
        "total_cents": order.get("total_cents"),
        "prep_units_total": order.get("prep_units_total"),
        "vicinity": order.get("vicinity"),
    })

def cancel_order(order_id: str):
    orders_repo, _, _ = _deps()
    order = orders_repo.get_order(order_id)
    if not order:
        return _resp(404, {"error": {"code": "NOT_FOUND"}})

    now = _now()

    try:
        plan = decide_cancel(order=order, now=now)   # <-- already exists in engine
    except (ExpiredError, InvalidStateError, NotFoundError) as e:
        spec = map_core_error(e)
        return _resp(spec.status_code, spec.body)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            orders_repo.update_order(**kwargs)
        except Exception:
            latest = orders_repo.get_order(order_id) or order
            # return latest stable state
            return _resp(200, {"order_id": order_id, "status": latest.get("status")})

    _log(
        "ORDER_CANCELED",
        order_id=order_id,
        restaurant_id=order.get("restaurant_id"),
        from_status=order.get("status"),
        canceled_at=now,
    )

    return _resp(200, plan.response or {"order_id": order_id, "status": order.get("status")})

def restaurant_set_status(restaurant_id: str, order_id: str, payload: dict):
    orders_repo, _, _ = _deps()

    target = payload.get("status")
    if not isinstance(target, str) or not target:
        return _resp(400, {"error": {"code": "VALIDATION", "message": "status is required"}})

    order = orders_repo.get_order(order_id)
    now = _now()

    try:
        plan = decide_restaurant_status_update(
            order=order,
            restaurant_id=restaurant_id,
            new_status=target,
            now=now,
        )

    except (ExpiredError, InvalidStateError, NotFoundError) as e:
        spec = map_core_error(e)
        return _resp(spec.status_code, spec.body)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            orders_repo.update_order(**kwargs)
        except Exception:
            latest = orders_repo.get_order(order_id) or order
            return _resp(200, {"order_id": order_id, "status": latest.get("status")})

    _log(
        "RESTAURANT_STATUS_UPDATE",
        order_id=order_id,
        restaurant_id=restaurant_id,
        from_status=order.get("status"),
        to_status=target,
        updated_at=now,
    )

    return _resp(200, plan.response or {"order_id": order_id, "status": order.get("status")})


# -------------------------
# List Orders
# -------------------------

def list_restaurant_orders(restaurant_id: str, status: str):
    orders_repo, config_repo, capacity_repo = _deps()
    items = orders_repo.query_by_restaurant_status(restaurant_id, status)
    items.sort(key=lambda x: x.get("sent_at", x.get("created_at", 0)))
    return _resp(200, {"restaurant_id": restaurant_id, "status": status, "orders": items})
