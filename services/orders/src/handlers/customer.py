"""
Customer-facing order handlers.

Handles: create, get, list, vicinity, cancel.
"""
import json
import base64
import time
import uuid
import math
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import engine
import capacity
import db
import location_bridge
from dynamo_apply import build_update_item_kwargs
from errors import NotFoundError
from models import (
    PAYMENT_MODE_AT_RESTAURANT,
    STATUS_PENDING,
    STATUS_WAITING,
)
from shared.logger import get_logger, Timer

log = get_logger("orders.customer", service="orders")
DISPATCH_ELIGIBLE_EVENTS = {'5_MIN_OUT', 'PARKING', 'AT_DOOR'}
DISPATCH_EVENT_PRIORITY = {
    '5_MIN_OUT': 1,
    'PARKING': 2,
    'AT_DOOR': 3,
}
VICINITY_DUPLICATE_COOLDOWN_SECONDS = 8
SAME_LOCATION_RADIUS_METERS_DEFAULT = 35
SAME_LOCATION_BOOTSTRAP_EVENT = 'AT_DOOR'
SAME_LOCATION_BOOTSTRAP_SOURCE = 'same_location_bootstrap'
SAME_LOCATION_NOTICE_CODE = 'ORDER_DISPATCHED_ON_SITE'
SAME_LOCATION_NOTICE_MESSAGE = (
    'Order placed immediately because you are already in the restaurant zone.'
)


def _normalize_arrival_event(value):
    normalized = str(value or '').strip().upper().replace('-', '_')
    if normalized == 'FIVE_MIN_OUT':
        normalized = '5_MIN_OUT'
    return normalized


def _event_priority(event_name):
    normalized = _normalize_arrival_event(event_name)
    return DISPATCH_EVENT_PRIORITY.get(normalized, 0)


def _to_int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_positive_int(value, fallback):
    parsed = _to_int_or_none(value)
    if parsed is None or parsed <= 0:
        return fallback
    return parsed


def _haversine_distance_meters(lat1, lon1, lat2, lon2):
    """
    Returns great-circle distance between two coordinates in meters.
    """
    earth_radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(d_lambda / 2.0) ** 2)
    )
    return 2.0 * earth_radius_m * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _extract_destination_coordinates(config_item):
    if not isinstance(config_item, dict):
        return None

    candidates = [
        (config_item.get('latitude'), config_item.get('longitude')),
        (config_item.get('lat'), config_item.get('lon')),
        (config_item.get('lat'), config_item.get('lng')),
    ]

    nested_location = config_item.get('location')
    if isinstance(nested_location, dict):
        candidates.extend([
            (nested_location.get('latitude'), nested_location.get('longitude')),
            (nested_location.get('lat'), nested_location.get('lon')),
            (nested_location.get('lat'), nested_location.get('lng')),
        ])

    for raw_lat, raw_lon in candidates:
        lat = location_bridge.coerce_finite_float(raw_lat)
        lon = location_bridge.coerce_finite_float(raw_lon)
        if lat is not None and lon is not None:
            return (lat, lon)

    return None


def _should_suppress_vicinity_event(session, incoming_event, now):
    """
    Suppress stale/duplicate arrival events to reduce noisy updates.
    """
    current_event = _normalize_arrival_event(session.get('arrival_status'))
    incoming = _normalize_arrival_event(incoming_event)
    status = session.get('status')

    if not current_event or not incoming:
        return (False, None)

    current_priority = _event_priority(current_event)
    incoming_priority = _event_priority(incoming)

    # Never let progression move backwards (e.g. AT_DOOR -> 5_MIN_OUT).
    if current_priority and incoming_priority and incoming_priority < current_priority:
        return (True, 'stale_arrival_regression')

    # Duplicate events after dispatch add no signal and should be ignored.
    if incoming == current_event and status not in (STATUS_PENDING, STATUS_WAITING):
        return (True, 'duplicate_event')

    # While still pending/waiting, allow retries but avoid hot-loop hammering.
    if incoming == current_event and status in (STATUS_PENDING, STATUS_WAITING):
        if VICINITY_DUPLICATE_COOLDOWN_SECONDS <= 0:
            return (False, None)
        last_update = _to_int_or_none(session.get('last_arrival_update'))
        if last_update is not None and (now - last_update) < VICINITY_DUPLICATE_COOLDOWN_SECONDS:
            return (True, 'duplicate_within_cooldown')

    return (False, None)


def _maybe_bootstrap_same_location_arrival(session, customer_id, latitude, longitude, now, req_log):
    """
    If customer is already physically at the destination when the order is created,
    geofence ENTER might never fire. This bootstrap path synthesizes AT_DOOR from
    location ingestion to avoid orders staying stuck in PENDING.
    """
    if not db.config_table:
        return None

    status = session.get('status')
    if status not in (STATUS_PENDING, STATUS_WAITING):
        return None

    current_arrival = _normalize_arrival_event(session.get('arrival_status'))
    current_priority = _event_priority(current_arrival)
    bootstrap_priority = _event_priority(SAME_LOCATION_BOOTSTRAP_EVENT)

    if status == STATUS_PENDING and current_priority >= bootstrap_priority:
        return None

    # WAITING orders still need periodic retries to grab newly freed capacity.
    if status == STATUS_WAITING and current_priority >= bootstrap_priority:
        last_update = _to_int_or_none(session.get('last_arrival_update'))
        if last_update is not None and (now - last_update) < VICINITY_DUPLICATE_COOLDOWN_SECONDS:
            return None

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    if not destination_id:
        return None

    try:
        resp = db.config_table.get_item(Key={'restaurant_id': destination_id})
        config_item = resp.get('Item', {}) if isinstance(resp, dict) else {}
    except Exception:
        return None

    destination_coords = _extract_destination_coordinates(config_item)
    if not destination_coords:
        return None

    dest_lat, dest_lon = destination_coords
    distance_m = _haversine_distance_meters(latitude, longitude, dest_lat, dest_lon)
    radius_m = _to_positive_int(
        config_item.get('same_location_radius_m'),
        SAME_LOCATION_RADIUS_METERS_DEFAULT,
    )

    if distance_m > radius_m:
        return None

    order_id = session.get('order_id', session.get('session_id'))
    if not order_id:
        return None

    req_log.info("same_location_bootstrap_triggered", extra={
        "event": SAME_LOCATION_BOOTSTRAP_EVENT,
        "distance_m": round(distance_m, 2),
        "radius_m": radius_m,
    })

    synthetic = {'body': json.dumps({
        'event': SAME_LOCATION_BOOTSTRAP_EVENT,
        'source': SAME_LOCATION_BOOTSTRAP_SOURCE,
    })}
    return update_vicinity(order_id, synthetic, customer_id)


def _build_same_location_notice(status):
    if status != 'SENT_TO_DESTINATION':
        return None
    return {
        'code': SAME_LOCATION_NOTICE_CODE,
        'message': SAME_LOCATION_NOTICE_MESSAGE,
    }


def _get_header(event, header_name):
    headers = event.get('headers') or {}
    if not isinstance(headers, dict):
        return None
    return (
        headers.get(header_name)
        or headers.get(header_name.lower())
        or headers.get(header_name.upper())
    )


def _sanitize_customer_name(name):
    if not isinstance(name, str):
        return None
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        return None
    return cleaned[:80]


def _resolve_customer_name(event, body_name=None):
    provided = _sanitize_customer_name(body_name)
    if provided:
        return provided

    claims = db.get_auth_claims(event)
    full_name = " ".join(
        part for part in [claims.get('given_name'), claims.get('family_name')] if part
    )
    claim_candidates = [
        claims.get('name'),
        claims.get('custom:name'),
        full_name,
        claims.get('preferred_username'),
        claims.get('cognito:username'),
        claims.get('email'),
    ]

    for candidate in claim_candidates:
        cleaned = _sanitize_customer_name(candidate)
        if cleaned:
            return cleaned

    return "Guest"


def create_order(event):
    req_log = log.bind(handler="create_order")
    req_log.info("create_order_started")

    # Idempotency Check
    idempotency_key = _get_header(event, 'Idempotency-Key')
    if idempotency_key and db.idempotency_table:
        req_log.info("idempotency_check", extra={"idempotency_key": idempotency_key})
        try:
            # 1. Try to lock the key
            db.idempotency_table.put_item(
                Item={
                    'idempotency_key': idempotency_key,
                    'status': 'PROCESSING',
                    'created_at': int(time.time()),
                    'ttl': int(time.time()) + 86400  # 24h retention
                },
                ConditionExpression='attribute_not_exists(idempotency_key)'
            )
            req_log.info("idempotency_lock_acquired", extra={"idempotency_key": idempotency_key})
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                # Key exists. Check if completed.
                entry = db.idempotency_table.get_item(
                    Key={'idempotency_key': idempotency_key},
                    ConsistentRead=True
                ).get('Item')
                
                if entry and entry.get('status') == 'COMPLETED':
                    req_log.info("idempotency_hit_completed", extra={"idempotency_key": idempotency_key})
                    return {
                        'statusCode': 201,
                        'headers': db.CORS_HEADERS,
                        'body': entry['body']
                    }
                else:
                    req_log.warning("idempotency_hit_in_progress", extra={"idempotency_key": idempotency_key})
                    return {'statusCode': 409, 'headers': db.CORS_HEADERS, 'body': json.dumps({'error': 'Request in progress'})}
            else:
                raise e

    # Proceed with creation
    try:
        body = json.loads(event.get('body', '{}'))
        restaurant_id = body.get('restaurant_id')
        items = body.get('items', [])
        payment_mode = body.get('payment_mode', PAYMENT_MODE_AT_RESTAURANT)

        if not restaurant_id:
            return {
                'statusCode': 400,
                'headers': db.cors_headers(event),
                'body': json.dumps({'error': 'restaurant_id is required'}),
            }

        req_log = req_log.bind(restaurant_id=restaurant_id)
        req_log.info("order_payload_parsed", extra={
            "item_count": len(items),
            "payment_mode": payment_mode,
        })

        # Product scope: only pay-at-restaurant flow is supported.
        if payment_mode != PAYMENT_MODE_AT_RESTAURANT:
            req_log.warning("unsupported_payment_mode", extra={"payment_mode": payment_mode})
            return {
                'statusCode': 400,
                'headers': db.cors_headers(event),
                'body': json.dumps({'error': 'Only PAY_AT_RESTAURANT is supported'})
            }

        # Validate
        engine.validate_resources_payload(items)

        # Integrity Check: Ensure restaurant exists
        if db.config_table:
            with Timer() as t:
                resp = db.config_table.get_item(Key={'restaurant_id': restaurant_id})
            req_log.info("restaurant_lookup", extra={"duration_ms": t.elapsed_ms, "found": 'Item' in resp})
            if 'Item' not in resp:
                return {'statusCode': 400, 'body': json.dumps({'error': f'Restaurant {restaurant_id} not found'})}
        else:
            req_log.warning("config_table_not_configured")

        now = int(time.time())
        order_id = f"ord_{uuid.uuid4().hex[:16]}"
        customer_id = db.get_customer_id(event)
        customer_name = _resolve_customer_name(event, body.get('customer_name'))

        req_log = req_log.bind(order_id=order_id, customer_id=customer_id, customer_name=customer_name)
        req_log.info("order_id_generated")

        # Create domain model
        order = engine.create_session_model(
            session_id=order_id,
            destination_id=restaurant_id,
            resources=items,
            customer_id=customer_id,
            now=now,
            expires_at=now + 3600,  # 1 hour expiry
            ttl=now + (90 * 24 * 60 * 60), # 90 days retention,
            payment_mode=PAYMENT_MODE_AT_RESTAURANT,
            customer_name=customer_name,
        )
        req_log.info("session_model_created", extra={"status": order.get("status")})

        # Save to DynamoDB
        if db.orders_table:
            # Convert floats to Decimal for DynamoDB
            item_db = json.loads(json.dumps(order), parse_float=Decimal)
            # CRITICAL FIX: Ensure partition key exists
            item_db['order_id'] = order_id
            # Ensure GSI keys exist
            item_db['restaurant_id'] = restaurant_id

            with Timer() as t:
                db.orders_table.put_item(Item=item_db)
            req_log.info("order_persisted", extra={"duration_ms": t.elapsed_ms})
        else:
            req_log.warning("orders_table_not_configured")

        # Ensure response has order_id (engine returns session_id)
        order['order_id'] = order_id
        
        resp_body = json.dumps(order, default=db.decimal_default)
        
        # Success: Update idempotency record
        if idempotency_key and db.idempotency_table:
            with Timer() as t:
                db.idempotency_table.update_item(
                    Key={'idempotency_key': idempotency_key},
                    UpdateExpression="SET #s = :s, body = :b",
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={
                        ':s': 'COMPLETED',
                        ':b': resp_body
                    }
                )
            req_log.info("idempotency_completed", extra={"duration_ms": t.elapsed_ms})

        req_log.info("create_order_success", extra={"order_id": order_id, "status": order.get("status")})
        return {
            'statusCode': 201,
            'headers': db.cors_headers(event),
            'body': resp_body
        }
    except Exception as e:
        req_log.error("create_order_failed", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        # Failure: Release lock
        if idempotency_key and db.idempotency_table:
            db.idempotency_table.delete_item(Key={'idempotency_key': idempotency_key})
            req_log.info("idempotency_lock_released")
        raise e


def get_order(order_id, customer_id=None):
    req_log = log.bind(handler="get_order", order_id=order_id, customer_id=customer_id)

    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.CORS_HEADERS, 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    item = resp.get('Item')

    req_log.info("order_fetched", extra={"found": item is not None, "duration_ms": t.elapsed_ms})

    if not item:
        raise NotFoundError()

    # Ownership check: customer can only see their own orders
    if customer_id and item.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": item.get('customer_id')})
        raise NotFoundError()

    return {
        'statusCode': 200,
        'headers': db.CORS_HEADERS,
        'body': json.dumps(item, default=db.decimal_default)
    }


def get_leave_advisory(order_id, customer_id=None):
    """
    Return a non-reserving leave-time estimate for a pending/waiting order.
    """
    req_log = log.bind(handler="get_leave_advisory", order_id=order_id, customer_id=customer_id)

    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.CORS_HEADERS, 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_fetched_for_advisory", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    # Ownership check: customer can only access their own order
    if customer_id and session.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": session.get('customer_id')})
        raise NotFoundError()

    status = session.get('status')
    now = int(time.time())

    # Advisory becomes informational-only once dispatch has already happened.
    if status not in (STATUS_PENDING, STATUS_WAITING):
        return {
            'statusCode': 200,
            'headers': db.CORS_HEADERS,
            'body': json.dumps({
                'order_id': order_id,
                'status': status,
                'recommended_action': 'FOLLOW_LIVE_STATUS',
                'estimated_wait_seconds': 0,
                'suggested_leave_at': now,
                'is_estimate': True,
                'advisory_note': 'Order is already dispatched or closed. Follow live status updates.'
            }, default=db.decimal_default)
        }

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    estimate = capacity.estimate_leave_advisory(
        capacity_table=db.capacity_table,
        config_table=db.config_table,
        destination_id=destination_id,
        now=now,
    )

    response = {
        'order_id': order_id,
        'status': status,
        **estimate,
    }

    return {
        'statusCode': 200,
        'headers': db.CORS_HEADERS,
        'body': json.dumps(response, default=db.decimal_default)
    }


def list_customer_orders(event):
    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.cors_headers(event), 'body': 'DB not configured'}

    customer_id = db.get_customer_id(event)
    req_log = log.bind(handler="list_customer_orders", customer_id=customer_id)

    query_params = event.get('queryStringParameters') or {}
    try:
        limit = min(int(query_params.get('limit', 25)), 100)
    except (ValueError, TypeError):
        limit = 25
    next_token = query_params.get('next_token')

    try:
        with Timer() as t:
            kwargs = {
                'IndexName': 'GSI_CustomerOrders',
                'KeyConditionExpression': Key('customer_id').eq(customer_id),
                'ScanIndexForward': False,
                'Limit': limit,
            }
            if next_token:
                try:
                    kwargs['ExclusiveStartKey'] = json.loads(
                        base64.b64decode(next_token).decode()
                    )
                except Exception:
                    return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid pagination token'})}

            resp = db.orders_table.query(**kwargs)

        items = resp.get('Items', [])
        result = {'orders': items}

        if 'LastEvaluatedKey' in resp:
            result['next_token'] = base64.b64encode(
                json.dumps(resp['LastEvaluatedKey'], default=db.decimal_default).encode()
            ).decode()

        req_log.info("orders_listed", extra={"count": len(items), "duration_ms": t.elapsed_ms})

        return {
            'statusCode': 200,
            'headers': db.cors_headers(event),
            'body': json.dumps(result, default=db.decimal_default)
        }
    except Exception as e:
        req_log.error("list_orders_failed", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        return {'statusCode': 500, 'headers': db.cors_headers(event), 'body': json.dumps({'error': 'Internal server error'})}


def ingest_location(order_id, event, customer_id=None):
    req_log = log.bind(handler="ingest_location", order_id=order_id, customer_id=customer_id)

    body = json.loads(event.get('body') or '{}')
    latitude = location_bridge.coerce_finite_float(
        body.get('latitude', body.get('lat'))
    )
    longitude = location_bridge.coerce_finite_float(
        body.get('longitude', body.get('lon'))
    )
    if latitude is None or longitude is None:
        req_log.warning("invalid_location_payload")
        return {'statusCode': 400, 'headers': db.cors_headers(event), 'body': json.dumps({'error': 'latitude/longitude are required numeric values'})}

    accuracy_m = location_bridge.coerce_finite_float(body.get('accuracy_m', body.get('accuracy')))
    speed_mps = location_bridge.coerce_finite_float(body.get('speed_mps', body.get('speed')))
    heading_deg = location_bridge.coerce_finite_float(body.get('heading_deg', body.get('heading')))

    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.cors_headers(event), 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')
    req_log.info("order_fetched_for_location", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    # Bind restaurant_id for all subsequent log lines
    req_log = req_log.bind(restaurant_id=session.get('destination_id', session.get('restaurant_id', '')))

    if customer_id and session.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": session.get('customer_id')})
        raise NotFoundError()

    now = int(time.time())
    sample_time_seconds = location_bridge.coerce_epoch_seconds(
        body.get('sample_time', body.get('timestamp')),
        fallback_now_seconds=now,
    )

    expr_values = {
        ':lat': Decimal(str(latitude)),
        ':lon': Decimal(str(longitude)),
        ':sample': sample_time_seconds,
        ':received': now,
        ':source': 'mobile_hybrid',
    }
    set_parts = [
        'last_location_lat = :lat',
        'last_location_lon = :lon',
        'last_location_sample_time = :sample',
        'last_location_received_at = :received',
        'last_location_source = :source',
    ]
    if accuracy_m is not None:
        expr_values[':acc'] = Decimal(str(accuracy_m))
        set_parts.append('last_location_accuracy_m = :acc')
    if speed_mps is not None:
        expr_values[':speed'] = Decimal(str(speed_mps))
        set_parts.append('last_location_speed_mps = :speed')
    if heading_deg is not None:
        expr_values[':heading'] = Decimal(str(heading_deg))
        set_parts.append('last_location_heading_deg = :heading')

    db.orders_table.update_item(
        Key={'order_id': order_id},
        UpdateExpression='SET ' + ', '.join(set_parts),
        ExpressionAttributeValues=expr_values,
    )

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    publish_result = location_bridge.publish_device_position(
        device_id=customer_id or session.get('customer_id') or order_id,
        latitude=latitude,
        longitude=longitude,
        sample_time_seconds=sample_time_seconds,
        position_properties={
            'order_id': order_id,
            'destination_id': destination_id,
            'source': 'mobile_hybrid',
        },
    )

    req_log.info("location_ingested", extra={
        "event": "location_sample",
        "detail": json.dumps({"published": bool(publish_result.get('published'))}),
    })

    same_location_bootstrap = _maybe_bootstrap_same_location_arrival(
        session=session,
        customer_id=customer_id,
        latitude=latitude,
        longitude=longitude,
        now=now,
        req_log=req_log,
    )

    response_body = {
        'order_id': order_id,
        'received': True,
        'sample_time': sample_time_seconds,
        'published_to_location': bool(publish_result.get('published')),
        'tracker_enabled': bool(publish_result.get('tracker_enabled')),
        'publish_reason': publish_result.get('reason'),
    }
    if same_location_bootstrap:
        response_body['same_location_bootstrap_status_code'] = same_location_bootstrap.get('statusCode')
        try:
            response_body['same_location_bootstrap'] = json.loads(
                same_location_bootstrap.get('body') or '{}'
            )
        except Exception:
            response_body['same_location_bootstrap'] = {
                'error': 'invalid_same_location_bootstrap_payload'
            }

    return {
        'statusCode': 202,
        'headers': db.cors_headers(event),
        'body': json.dumps(response_body, default=db.decimal_default),
    }


def update_vicinity(order_id, event, customer_id=None):
    body = json.loads(event.get('body', '{}'))
    vicinity_event = body.get('event')
    event_source = str(body.get('source') or '').strip().lower()

    req_log = log.bind(handler="update_vicinity", order_id=order_id, customer_id=customer_id)
    req_log.info("vicinity_update_started", extra={"event": vicinity_event})

    # Validate vicinity event type
    if vicinity_event not in db.VALID_VICINITY_EVENTS:
        req_log.warning("invalid_vicinity_event", extra={"event": vicinity_event})
        return {'statusCode': 400, 'headers': db.cors_headers(event), 'body': json.dumps({'error': f'Invalid vicinity event: {vicinity_event}'})}

    # Fetch current state
    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.cors_headers(event)}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_state_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    # Bind restaurant_id for all subsequent log lines
    req_log = req_log.bind(restaurant_id=session.get('destination_id', session.get('restaurant_id', '')))

    # Ownership check
    if customer_id and session.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": session.get('customer_id')})
        raise NotFoundError()

    current_status = session.get('status')
    req_log.info("current_order_state", extra={"status": current_status})

    now = int(time.time())
    
    # Check expiry before processing
    engine.ensure_not_expired(session, now)

    suppress_event, suppress_reason = _should_suppress_vicinity_event(session, vicinity_event, now)
    if suppress_event:
        req_log.info("vicinity_update_suppressed", extra={
            "event": vicinity_event,
            "reason": suppress_reason,
            "status": current_status,
            "arrival_status": session.get('arrival_status'),
        })
        return {
            'statusCode': 200,
            'headers': db.cors_headers(event),
            'body': json.dumps({
                "session_id": session.get("session_id", session.get("order_id")),
                "status": current_status,
                "arrival_status": session.get("arrival_status"),
                "suppressed": True,
                "suppression_reason": suppress_reason,
            }, default=db.decimal_default),
        }

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    config = capacity.get_capacity_config(db.config_table, destination_id)
    dispatch_trigger_event = capacity.normalize_dispatch_trigger_event(
        config.get('dispatch_trigger_event')
    )
    event_priority = DISPATCH_EVENT_PRIORITY.get(vicinity_event, 0)
    trigger_priority = DISPATCH_EVENT_PRIORITY.get(dispatch_trigger_event, 1)

    # Dispatch transition must reserve capacity for a dispatch-eligible arrival
    # event that meets the restaurant-configured trigger threshold.
    cap_result = None
    is_dispatch_candidate = (
        vicinity_event in DISPATCH_ELIGIBLE_EVENTS and
        current_status in (STATUS_PENDING, STATUS_WAITING) and
        event_priority >= trigger_priority
    )

    if is_dispatch_candidate:
        req_log.info("dispatch_capacity_check_started", extra={"restaurant_id": destination_id, "event": vicinity_event})

        if db.capacity_table:
            with Timer() as t:
                cap_result = capacity.check_and_reserve_for_arrival(
                    capacity_table=db.capacity_table,
                    config_table=db.config_table,
                    destination_id=destination_id,
                    now=now,
                )
            req_log.info("dispatch_capacity_check_completed", extra={
                "reserved": cap_result.get('reserved'),
                "window_start": cap_result.get('window_start'),
                "window_seconds": cap_result.get('window_seconds'),
                "duration_ms": t.elapsed_ms,
            })
        else:
            # If capacity table is unavailable, dispatch path remains open
            # (no reservation guarantee).
            cfg = capacity.get_capacity_config(db.config_table, destination_id)
            window_seconds = int(cfg.get('capacity_window_seconds', capacity.DEFAULT_WINDOW_SECONDS))
            cap_result = {
                'reserved': True,
                'window_start': capacity.get_window_start(now, window_seconds),
                'window_seconds': window_seconds,
                'max_concurrent': int(cfg.get('max_concurrent_orders', capacity.DEFAULT_MAX_CONCURRENT)),
            }
            req_log.warning("capacity_table_missing_dispatching_without_reservation")

        plan = engine.decide_vicinity_update(
            session=session,
            vicinity=True,
            now=now,
            window_seconds=cap_result['window_seconds'],
            window_start=cap_result['window_start'],
            reserved_capacity=cap_result['reserved'],
        )

        # Preserve arrival progression metadata even on the capacity path.
        if plan.set_fields is not None:
            plan.set_fields['arrival_status'] = vicinity_event
            plan.set_fields['last_arrival_update'] = now
        if plan.response is not None:
            plan.response['arrival_status'] = vicinity_event
    else:
        # Non-dispatch events (or events below trigger threshold) use arrival-only path.
        plan = engine.decide_arrival_update(
            session,
            vicinity_event,
            now,
            allow_dispatch_transition=False,
        )

    if cap_result:
        req_log.info("capacity_decision", extra={
            "reserved": cap_result.get('reserved'),
            "window_start": cap_result.get('window_start'),
            "window_seconds": cap_result.get('window_seconds'),
        })

    req_log.info("state_transition_decided", extra={
        "new_status": plan.response.get('status'),
        "has_error": bool(plan.response.get('error')),
    })

    # Apply updates
    if plan.response.get('error'):
        req_log.warning("vicinity_update_rejected", extra={"error": plan.response.get('error')})
        return {'statusCode': 400, 'body': json.dumps(plan.response)}

    if event_source == SAME_LOCATION_BOOTSTRAP_SOURCE:
        notice = _build_same_location_notice(plan.response.get('status'))
        if notice:
            req_log.info("same_location_notice_attached", extra={
                "code": notice.get("code"),
                "status": plan.response.get('status'),
            })
            if plan.response is not None:
                plan.response['customer_notice'] = notice
            if plan.set_fields is not None:
                plan.set_fields['customer_notice_code'] = notice.get('code')
                plan.set_fields['customer_notice_message'] = notice.get('message')
                plan.set_fields['customer_notice_at'] = now

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            with Timer() as t:
                db.orders_table.update_item(**kwargs)
            req_log.info("order_updated", extra={"duration_ms": t.elapsed_ms, "new_status": plan.response.get('status')})
        except db.orders_table.meta.client.exceptions.ConditionalCheckFailedException:
            # TOCTOU race: another request already transitioned this order.
            # Release the capacity slot we reserved to prevent phantom exhaustion.
            req_log.warning("conditional_check_failed_race", extra={"order_id": order_id})
            if cap_result and cap_result.get('reserved'):
                try:
                    capacity.release_slot(
                        db.capacity_table,
                        session.get('destination_id', session.get('restaurant_id')),
                        cap_result['window_start']
                    )
                    req_log.info("capacity_rollback_on_race_success")
                except Exception as rollback_err:
                    req_log.error("capacity_rollback_on_race_failed", extra={"detail": str(rollback_err)})
            # Re-read order to return the current state (set by the winning request)
            refreshed = db.orders_table.get_item(Key={'order_id': order_id}).get('Item', {})
            return {
                'statusCode': 200,
                'headers': db.cors_headers(event),
                'body': json.dumps({
                    'status': refreshed.get('status'),
                    'arrival_status': refreshed.get('arrival_status'),
                    'idempotent': True,
                }, default=db.decimal_default)
            }
        except Exception as e:
            req_log.error("order_update_failed", extra={"error_type": type(e).__name__, "detail": str(e)})
            # Capacity rollback on failure
            if cap_result and cap_result.get('reserved'):
                try:
                    capacity.release_slot(
                        db.capacity_table,
                        session.get('destination_id', session.get('restaurant_id')),
                        cap_result['window_start']
                    )
                    req_log.info("capacity_rollback_success")
                except Exception as rollback_err:
                    req_log.error("capacity_rollback_failed", extra={"detail": str(rollback_err)})
            raise e

    req_log.info("vicinity_update_completed", extra={
        "event": vicinity_event,
        "new_status": plan.response.get('status'),
    })

    return {
        'statusCode': 200,
        'headers': db.cors_headers(event),
        'body': json.dumps(plan.response, default=db.decimal_default)
    }


def cancel_order(order_id, customer_id=None):
    req_log = log.bind(handler="cancel_order", order_id=order_id, customer_id=customer_id)
    req_log.info("cancel_order_started")

    if not db.orders_table:
        return {'statusCode': 500, 'headers': db.CORS_HEADERS, 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    # Bind restaurant_id for all subsequent log lines
    req_log = req_log.bind(restaurant_id=session.get('destination_id', session.get('restaurant_id', '')))

    # Ownership check
    if customer_id and session.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": session.get('customer_id')})
        raise NotFoundError()

    current_status = session.get('status')
    req_log.info("current_order_state", extra={"status": current_status})

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)
    
    plan = engine.decide_cancel(session, now)
    req_log.info("cancel_decision", extra={"new_status": plan.response.get('status')})

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            with Timer() as t:
                db.orders_table.update_item(**kwargs)
            req_log.info("order_canceled_in_db", extra={"duration_ms": t.elapsed_ms})
        except db.orders_table.meta.client.exceptions.ConditionalCheckFailedException:
            req_log.warning("cancel_race_lost", extra={"order_id": order_id})
            return {
                'statusCode': 409,
                'headers': db.CORS_HEADERS,
                'body': json.dumps({'error': 'Order has already been dispatched and cannot be cancelled'}),
            }

    # Release capacity slot if one was reserved
    db.release_capacity_slot(session)
    req_log.info("capacity_slot_released")

    req_log.info("cancel_order_completed", extra={"order_id": order_id, "new_status": plan.response.get('status')})
    return {
        'statusCode': 200,
        'headers': db.CORS_HEADERS,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }
