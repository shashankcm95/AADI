"""
Customer-facing order handlers.

Handles: create, get, list, vicinity, cancel.
"""
import json
import base64
import time
import uuid
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import engine
import capacity
import db
from dynamo_apply import build_update_item_kwargs
from errors import NotFoundError
from models import PAYMENT_MODE_AT_RESTAURANT
from logger import get_logger, Timer

log = get_logger("orders.customer", service="orders")


def create_order(event):
    req_log = log.bind(handler="create_order")
    req_log.info("create_order_started")

    # Idempotency Check
    idempotency_key = event.get('headers', {}).get('Idempotency-Key')
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
                        'headers': {'Content-Type': 'application/json'},
                        'body': entry['body']
                    }
                else:
                    req_log.warning("idempotency_hit_in_progress", extra={"idempotency_key": idempotency_key})
                    return {'statusCode': 409, 'body': json.dumps({'error': 'Request in progress'})}
            else:
                raise e

    # Proceed with creation
    try:
        body = json.loads(event.get('body', '{}'))
        restaurant_id = body.get('restaurant_id')
        items = body.get('items', [])
        payment_mode = body.get('payment_mode', PAYMENT_MODE_AT_RESTAURANT)

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

        req_log = req_log.bind(order_id=order_id, customer_id=customer_id)
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
            payment_mode=PAYMENT_MODE_AT_RESTAURANT
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
            'headers': {'Content-Type': 'application/json'},
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
        return {'statusCode': 500, 'body': 'DB not configured'}

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
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(item, default=db.decimal_default)
    }


def list_customer_orders(event):
    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

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
                kwargs['ExclusiveStartKey'] = json.loads(
                    base64.b64decode(next_token).decode()
                )

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
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, default=db.decimal_default)
        }
    except Exception as e:
        req_log.error("list_orders_failed", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def update_vicinity(order_id, event, customer_id=None):
    body = json.loads(event.get('body', '{}'))
    vicinity_event = body.get('event')

    req_log = log.bind(handler="update_vicinity", order_id=order_id, customer_id=customer_id)
    req_log.info("vicinity_update_started", extra={"event": vicinity_event})

    # Validate vicinity event type
    if vicinity_event not in db.VALID_VICINITY_EVENTS:
        req_log.warning("invalid_vicinity_event", extra={"event": vicinity_event})
        return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid vicinity event: {vicinity_event}'})}

    # Fetch current state
    if not db.orders_table:
        return {'statusCode': 500}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_state_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    # Ownership check
    if customer_id and session.get('customer_id') != customer_id:
        req_log.warning("ownership_check_failed", extra={"order_customer": session.get('customer_id')})
        raise NotFoundError()

    current_status = session.get('status')
    req_log.info("current_order_state", extra={"status": current_status})

    now = int(time.time())
    
    # Check expiry before processing
    engine.ensure_not_expired(session, now)

    # --- Capacity-gated path for 5_MIN_OUT ---
    cap_result = None
    if vicinity_event == '5_MIN_OUT' and db.capacity_table:
        destination_id = session.get('destination_id', session.get('restaurant_id'))
        req_log.info("capacity_check_started", extra={"restaurant_id": destination_id})

        with Timer() as t:
            cap_result = capacity.check_and_reserve_for_arrival(
                capacity_table=db.capacity_table,
                config_table=db.config_table,
                destination_id=destination_id,
                now=now,
            )
        req_log.info("capacity_check_completed", extra={
            "reserved": cap_result.get('reserved'),
            "window_start": cap_result.get('window_start'),
            "window_seconds": cap_result.get('window_seconds'),
            "duration_ms": t.elapsed_ms,
        })

        plan = engine.decide_vicinity_update(
            session=session,
            vicinity=True,
            now=now,
            window_seconds=cap_result['window_seconds'],
            window_start=cap_result['window_start'],
            reserved_capacity=cap_result['reserved'],
        )
    else:
        # Non-capacity events: PARKING, AT_DOOR, EXIT_VICINITY
        plan = engine.decide_arrival_update(session, vicinity_event, now)

    req_log.info("state_transition_decided", extra={
        "new_status": plan.response.get('status'),
        "has_error": bool(plan.response.get('error')),
    })

    # Apply updates
    if plan.response.get('error'):
        req_log.warning("vicinity_update_rejected", extra={"error": plan.response.get('error')})
        return {'statusCode': 400, 'body': json.dumps(plan.response)}

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            with Timer() as t:
                db.orders_table.update_item(**kwargs)
            req_log.info("order_updated", extra={"duration_ms": t.elapsed_ms, "new_status": plan.response.get('status')})
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
        'body': json.dumps(plan.response, default=db.decimal_default)
    }


def cancel_order(order_id, customer_id=None):
    req_log = log.bind(handler="cancel_order", order_id=order_id, customer_id=customer_id)
    req_log.info("cancel_order_started")

    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

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
        with Timer() as t:
            db.orders_table.update_item(**kwargs)
        req_log.info("order_canceled_in_db", extra={"duration_ms": t.elapsed_ms})

    # Release capacity slot if one was reserved
    db.release_capacity_slot(session)
    req_log.info("capacity_slot_released")

    req_log.info("cancel_order_completed", extra={"order_id": order_id, "new_status": plan.response.get('status')})
    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }

