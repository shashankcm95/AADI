"""
Restaurant-side order handlers.

Handles: list restaurant orders, acknowledge, update status.
"""
import json
import base64
import time
from boto3.dynamodb.conditions import Key

import engine
import models
import db
from dynamo_apply import build_update_item_kwargs
from errors import NotFoundError
from logger import get_logger, Timer

log = get_logger("orders.restaurant", service="orders")


def list_restaurant_orders(restaurant_id, event):
    req_log = log.bind(handler="list_restaurant_orders", restaurant_id=restaurant_id)

    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    query_params = event.get('queryStringParameters') or {}
    status = query_params.get('status')
    try:
        limit = min(int(query_params.get('limit', 25)), 100)
    except (ValueError, TypeError):
        limit = 25
    next_token = query_params.get('next_token')
    req_log.info("listing_orders", extra={"status_filter": status, "limit": limit})

    try:
        with Timer() as t:
            kwargs = {'Limit': limit}
            if next_token:
                kwargs['ExclusiveStartKey'] = json.loads(
                    base64.b64decode(next_token).decode()
                )

            if status:
                kwargs.update({
                    'IndexName': 'GSI_RestaurantStatus',
                    'KeyConditionExpression': Key('restaurant_id').eq(restaurant_id) & Key('status').eq(status),
                })
            else:
                kwargs.update({
                    'IndexName': 'GSI_RestaurantStatus',
                    'KeyConditionExpression': Key('restaurant_id').eq(restaurant_id),
                })

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


def ack_order(order_id, restaurant_id):
    req_log = log.bind(handler="ack_order", order_id=order_id, restaurant_id=restaurant_id)
    req_log.info("ack_order_started")

    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    current_status = session.get('status')
    req_log.info("current_state", extra={"status": current_status})

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)
    
    plan = engine.decide_ack_upgrade(session, restaurant_id, now)
    req_log.info("ack_decision", extra={"new_status": plan.response.get('status')})

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        with Timer() as t:
            db.orders_table.update_item(**kwargs)
        req_log.info("order_acknowledged", extra={"duration_ms": t.elapsed_ms})

    req_log.info("ack_order_completed", extra={"new_status": plan.response.get('status')})
    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }


def update_order_status(order_id, restaurant_id, event):
    req_log = log.bind(handler="update_order_status", order_id=order_id, restaurant_id=restaurant_id)

    if not db.orders_table:
        return {'statusCode': 500}

    if not restaurant_id:
        req_log.warning("missing_restaurant_id")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Missing restaurant_id'})}

    body = json.loads(event.get('body', '{}'))
    new_status = body.get('status')

    if not new_status:
        req_log.warning("missing_status")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Missing status'})}

    req_log.info("status_update_started", extra={"requested_status": new_status})

    # Fetch session first
    with Timer() as t:
        resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    req_log.info("order_fetched", extra={"found": session is not None, "duration_ms": t.elapsed_ms})

    if not session:
        raise NotFoundError()

    current_status = session.get('status')
    req_log.info("state_transition", extra={"from": current_status, "to": new_status})

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)

    # Enforce destination ownership in engine decision path.
    plan = engine.decide_destination_status_update(
        session=session,
        destination_id=restaurant_id,
        new_status=new_status,
        now=now
    )

    try:
        kwargs = build_update_item_kwargs(order_id, plan)
        if kwargs:
            with Timer() as t:
                db.orders_table.update_item(**kwargs)
            req_log.info("status_updated_in_db", extra={"duration_ms": t.elapsed_ms})

        # Release capacity slot when order is completed
        final_status = plan.set_fields.get('status') if plan.set_fields else session.get('status')
        if final_status in ('COMPLETED', models.STATUS_COMPLETED):
            db.release_capacity_slot(session)
            req_log.info("capacity_slot_released", extra={"order_id": order_id})

        req_log.info("status_update_completed", extra={"final_status": final_status})
        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'status': final_status})
        }
    except Exception as e:
        req_log.error("status_update_failed", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        raise e

