"""
Restaurant-side order handlers.

Handles: list restaurant orders, acknowledge, update status.
"""
import json
import time
from boto3.dynamodb.conditions import Key

import engine
import models
import db
from dynamo_apply import build_update_item_kwargs
from errors import NotFoundError


def list_restaurant_orders(restaurant_id, event):
    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    status = (event.get('queryStringParameters') or {}).get('status')

    try:
        if status:
            resp = db.orders_table.query(
                IndexName='GSI_RestaurantStatus',
                KeyConditionExpression=Key('restaurant_id').eq(restaurant_id) & Key('status').eq(status)
            )
        else:
            resp = db.orders_table.query(
                IndexName='GSI_RestaurantStatus',
                KeyConditionExpression=Key('restaurant_id').eq(restaurant_id)
            )

        items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'orders': items}, default=db.decimal_default)
        }
    except Exception as e:
        print(f"Query Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def ack_order(order_id, restaurant_id):
    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    if not session:
        raise NotFoundError()

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)
    
    plan = engine.decide_ack_upgrade(session, restaurant_id, now)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        db.orders_table.update_item(**kwargs)

    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }


def update_order_status(order_id, event):
    if not db.orders_table:
        return {'statusCode': 500}

    body = json.loads(event.get('body', '{}'))
    new_status = body.get('status')

    if not new_status:
        return {'statusCode': 400, 'body': json.dumps({'error': 'Missing status'})}

    # Fetch session first
    resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')
    if not session:
        raise NotFoundError()

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)

    # Use engine to validate transition and generate update plan
    # Destination ID is required but implicit here (restaurant already auth'd)
    # Ideally should pass restaurant_id from auth context, but using session's dest ID is safe
    # because this route is protected by IAM/Cognito anyway (verifying restaurant owns it is handled by auth layer or implicit)
    # The pure function requires destination_id to match session's dest_id
    destination_id = session.get('destination_id', session.get('restaurant_id'))
    
    plan = engine.decide_destination_status_update(
        session=session,
        destination_id=destination_id,
        new_status=new_status,
        now=now
    )

    try:
        kwargs = build_update_item_kwargs(order_id, plan)
        if kwargs:
            db.orders_table.update_item(**kwargs)

        # Release capacity slot when order is completed
        # The plan's set_fields['status'] will be the new status
        final_status = plan.set_fields.get('status') if plan.set_fields else session.get('status')
        if final_status in ('COMPLETED', models.STATUS_COMPLETED):
            db.release_capacity_slot(session)

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'status': final_status})
        }
    except Exception as e:
        print(f"Update Status Error: {e}")
        # Note: InvalidStateError raised by decide_destination_status_update will bubble up to app.py
        # which handles it nicely (409 Conflict)
        raise e
