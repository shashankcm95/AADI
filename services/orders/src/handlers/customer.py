"""
Customer-facing order handlers.

Handles: create, get, list, vicinity, tip, cancel.
"""
import json
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


def create_order(event):
    # Idempotency Check
    idempotency_key = event.get('headers', {}).get('Idempotency-Key')
    if idempotency_key and db.idempotency_table:
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
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                # Key exists. Check if completed.
                # Use consistent read to ensure we see latest state
                entry = db.idempotency_table.get_item(
                    Key={'idempotency_key': idempotency_key},
                    ConsistentRead=True
                ).get('Item')
                
                if entry and entry.get('status') == 'COMPLETED':
                     return {
                        'statusCode': 201, # Or entry['status_code'] if we stored it
                        'headers': {'Content-Type': 'application/json'},
                        'body': entry['body']
                    }
                else:
                    # Still processing or failed logic
                    return {'statusCode': 409, 'body': json.dumps({'error': 'Request in progress'})}
            else:
                raise e

    # Proceed with creation
    try:
        body = json.loads(event.get('body', '{}'))
        restaurant_id = body.get('restaurant_id')
        items = body.get('items', [])
        payment_mode = body.get('payment_mode', 'PAY_AT_RESTAURANT')

        # Validate
        engine.validate_resources_payload(items)

        now = int(time.time())
        order_id = f"ord_{uuid.uuid4().hex[:16]}"
        customer_id = db.get_customer_id(event)

        # Create domain model
        order = engine.create_session_model(
            session_id=order_id,
            destination_id=restaurant_id,
            resources=items,
            customer_id=customer_id,
            now=now,
            expires_at=now + 3600,  # 1 hour expiry
            payment_mode=payment_mode
        )

        # Save to DynamoDB
        if db.orders_table:
            # Convert floats to Decimal for DynamoDB
            item_db = json.loads(json.dumps(order), parse_float=Decimal)
            # CRITICAL FIX: Ensure partition key exists
            item_db['order_id'] = order_id
            # Ensure GSI keys exist
            item_db['restaurant_id'] = restaurant_id

            db.orders_table.put_item(Item=item_db)
        else:
            print("WARNING: Tables not configured")

        # Ensure response has order_id (engine returns session_id)
        order['order_id'] = order_id
        
        resp_body = json.dumps(order, default=db.decimal_default)
        
        # Success: Update idempotency record
        if idempotency_key and db.idempotency_table:
            db.idempotency_table.update_item(
                Key={'idempotency_key': idempotency_key},
                UpdateExpression="SET #s = :s, body = :b",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': 'COMPLETED',
                    ':b': resp_body
                }
            )

        return {
            'statusCode': 201,
            'headers': {'Content-Type': 'application/json'},
            'body': resp_body
        }
    except Exception as e:
        # Failure: Release lock
        if idempotency_key and db.idempotency_table:
            db.idempotency_table.delete_item(Key={'idempotency_key': idempotency_key})
        raise e


def get_order(order_id, customer_id=None):
    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    resp = db.orders_table.get_item(Key={'order_id': order_id})
    item = resp.get('Item')

    if not item:
        raise NotFoundError()

    # Ownership check: customer can only see their own orders
    if customer_id and item.get('customer_id') != customer_id:
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

    try:
        resp = db.orders_table.query(
            IndexName='GSI_CustomerOrders',
            KeyConditionExpression=Key('customer_id').eq(customer_id),
            ScanIndexForward=False
        )

        items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'orders': items}, default=db.decimal_default)
        }
    except Exception as e:
        print(f"Customer Query Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def update_vicinity(order_id, event, customer_id=None):
    body = json.loads(event.get('body', '{}'))
    vicinity_event = body.get('event')

    # Validate vicinity event type
    if vicinity_event not in db.VALID_VICINITY_EVENTS:
        return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid vicinity event: {vicinity_event}'})}

    # Fetch current state
    if not db.orders_table:
        return {'statusCode': 500}

    resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    if not session:
        raise NotFoundError()

    # Ownership check
    if customer_id and session.get('customer_id') != customer_id:
        raise NotFoundError()

    now = int(time.time())
    
    # Check expiry before processing
    engine.ensure_not_expired(session, now)

    # --- Capacity-gated path for 5_MIN_OUT ---
    cap_result = None
    if vicinity_event == '5_MIN_OUT' and db.capacity_table:
        destination_id = session.get('destination_id', session.get('restaurant_id'))
        cap_result = capacity.check_and_reserve_for_arrival(
            capacity_table=db.capacity_table,
            config_table=db.config_table,
            destination_id=destination_id,
            now=now,
        )

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

    # Apply updates
    if plan.response.get('error'):
        return {'statusCode': 400, 'body': json.dumps(plan.response)}

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        try:
            db.orders_table.update_item(**kwargs)
        except Exception as e:
            # Capacity rollback on failure
            if cap_result and cap_result.get('reserved'):
                try:
                    capacity.release_slot(
                        db.capacity_table,
                        session.get('destination_id', session.get('restaurant_id')),
                        cap_result['window_start']
                    )
                except Exception as rollback_err:
                     print(f"ROLLBACK FAILED: {rollback_err}")
            raise e

    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }


def add_tip(order_id, event, customer_id=None):
    if not db.orders_table:
        return {'statusCode': 500}

    # Fetch and verify ownership before updating
    resp = db.orders_table.get_item(Key={'order_id': order_id})
    item = resp.get('Item')
    if not item:
        raise NotFoundError()
    if customer_id and item.get('customer_id') != customer_id:
        raise NotFoundError()

    # Check expiry
    now = int(time.time())
    engine.ensure_not_expired(item, now)

    body = json.loads(event.get('body', '{}'))
    tip_cents = body.get('tip_cents', 0)

    db.orders_table.update_item(
        Key={'order_id': order_id},
        UpdateExpression="SET tip_cents = :t",
        ExpressionAttributeValues={':t': tip_cents}
    )

    return {
        'statusCode': 200,
        'body': json.dumps({'success': True})
    }


def cancel_order(order_id, customer_id=None):
    if not db.orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    resp = db.orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    if not session:
        raise NotFoundError()

    # Ownership check
    if customer_id and session.get('customer_id') != customer_id:
        raise NotFoundError()

    now = int(time.time())
    
    # Check expiry
    engine.ensure_not_expired(session, now)
    
    plan = engine.decide_cancel(session, now)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        db.orders_table.update_item(**kwargs)

    # Release capacity slot if one was reserved
    db.release_capacity_slot(session)

    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=db.decimal_default)
    }
