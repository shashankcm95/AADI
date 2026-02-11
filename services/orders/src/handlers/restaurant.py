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

    # Validate against allowlist
    if new_status not in db.VALID_RESTAURANT_STATUSES:
        return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid status: {new_status}'})}

    # Fetch session first so we can release capacity on completion
    resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')
    if not session:
        raise NotFoundError()

    try:
        db.orders_table.update_item(
            Key={'order_id': order_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': new_status},
            ConditionExpression="attribute_exists(order_id)"
        )

        # Release capacity slot when order is completed
        if new_status in ('COMPLETED', models.STATUS_COMPLETED):
            db.release_capacity_slot(session)

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'status': new_status})
        }
    except Exception as e:
        print(f"Update Status Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
