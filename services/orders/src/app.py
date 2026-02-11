import json
import os
import boto3
import time
import uuid
import traceback
from decimal import Decimal
from typing import Dict, Any
from boto3.dynamodb.conditions import Key

# Import domain logic
# Lambda runs this as main, so relative imports fail
import engine
import models
import capacity
from dynamo_apply import build_update_item_kwargs
from errors import NotFoundError, InvalidStateError, ValidationError, ExpiredError

# CORS headers for all responses (API Gateway handles preflight)
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
}

def make_response(status_code, body):
    """Helper to build a response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str)
    }

# Initialize DynamoDB resources
dynamodb = boto3.resource('dynamodb')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE')
CAPACITY_TABLE = os.environ.get('CAPACITY_TABLE')
RESTAURANT_CONFIG_TABLE = os.environ.get('RESTAURANT_CONFIG_TABLE')

orders_table = dynamodb.Table(ORDERS_TABLE) if ORDERS_TABLE else None
capacity_table = dynamodb.Table(CAPACITY_TABLE) if CAPACITY_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def lambda_handler(event, context):
    """
    Entry point for Orders Service Lambda
    """
    print(f"Event: {json.dumps(event)}")
    
    # Determine routing
    # HttpApi events have 'routeKey'
    route_key = event.get('routeKey')
    print(f"DEBUG_ROUTE_KEY: {route_key}")
    path_params = event.get('pathParameters', {})
    
    try:
        if route_key == 'POST /v1/orders':
            return create_order(event)
        
        elif route_key == 'GET /v1/orders/{order_id}':
            return get_order(path_params.get('order_id'))

        elif route_key == 'GET /v1/orders':
            return list_customer_orders(event)
            
        elif route_key == 'POST /v1/orders/{order_id}/vicinity':
            return update_vicinity(path_params.get('order_id'), event)
            
        elif route_key == 'POST /v1/orders/{order_id}/tip':
            return add_tip(path_params.get('order_id'), event)

        elif route_key == 'POST /v1/orders/{order_id}/cancel':
            return cancel_order(path_params.get('order_id'))

        elif route_key == 'GET /v1/restaurants/{restaurant_id}/orders':
            return list_restaurant_orders(path_params.get('restaurant_id'), event)

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack':
            return ack_order(path_params.get('order_id'), path_params.get('restaurant_id'))

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status':
            return update_order_status(path_params.get('order_id'), event)
        
        else:
            return make_response(404, {'error': 'Route not found'})
            
    except NotFoundError:
        return make_response(404, {'error': 'Not Found'})
    except InvalidStateError as e:
        return make_response(409, {'error': str(e)})
    except ExpiredError as e:
        return make_response(409, {'error': str(e)})
    except ValidationError as e:
        return make_response(400, {'error': str(e)})
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return make_response(500, {'error': 'Internal server error'})


def get_customer_id(event):
    """
    Extract customer ID from Cognito auth claims.
    Falls back to 'cust_demo' only if auth is missing (local testing).
    """
    try:
        # HTTP API (v2) format
        return event['requestContext']['authorizer']['jwt']['claims']['sub']
    except (KeyError, TypeError):
        try:
            # REST API (v1) format or other authorizers
            return event['requestContext']['authorizer']['claims']['sub']
        except (KeyError, TypeError):
            print("WARNING: No auth context found. Using 'cust_demo'.")
            return "cust_demo"


def create_order(event):
    body = json.loads(event.get('body', '{}'))
    restaurant_id = body.get('restaurant_id')
    items = body.get('items', [])
    payment_mode = body.get('payment_mode', 'PAY_AT_RESTAURANT')
    
    # Validate
    engine.validate_resources_payload(items)
    
    now = int(time.time())
    order_id = f"ord_{uuid.uuid4().hex[:16]}"
    customer_id = get_customer_id(event)
    
    # Create domain model
    order = engine.create_session_model(
        session_id=order_id,
        destination_id=restaurant_id,
        resources=items,
        customer_id=customer_id,
        now=now,
        expires_at=now + 3600, # 1 hour expiry
        payment_mode=payment_mode
    )
    
    # Save to DynamoDB
    if orders_table:
        # Convert floats to Decimal for DynamoDB
        item_db = json.loads(json.dumps(order), parse_float=Decimal)
        # CRITICAL FIX: Ensure partition key exists
        item_db['order_id'] = order_id
        # Ensure GSI keys exist
        item_db['restaurant_id'] = restaurant_id
        
        orders_table.put_item(Item=item_db)
    else:
        print("WARNING: Tables not configured")
    
    # Ensure response has order_id (engine returns session_id)
    order['order_id'] = order_id
        
    return {
        'statusCode': 201,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(order, default=decimal_default)
    }

def get_order(order_id):
    if not orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}
        
    resp = orders_table.get_item(Key={'order_id': order_id})
    item = resp.get('Item')
    
    if not item:
        raise NotFoundError()
        
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(item, default=decimal_default)
    }


def list_customer_orders(event):
    if not orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}
        
    customer_id = get_customer_id(event)
    
    try:
        # Query using the new GSI
        # ScanIndexForward=False ensures newest orders first
        resp = orders_table.query(
            IndexName='GSI_CustomerOrders',
            KeyConditionExpression=Key('customer_id').eq(customer_id),
            ScanIndexForward=False
        )
            
        items = resp.get('Items', [])
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'orders': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Customer Query Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

def list_restaurant_orders(restaurant_id, event):
    if not orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}
        
    status = (event.get('queryStringParameters') or {}).get('status')
    
    try:
        if status:
            resp = orders_table.query(
                IndexName='GSI_RestaurantStatus',
                KeyConditionExpression=Key('restaurant_id').eq(restaurant_id) & Key('status').eq(status)
            )
        else:
            resp = orders_table.query(
                IndexName='GSI_RestaurantStatus',
                KeyConditionExpression=Key('restaurant_id').eq(restaurant_id)
            )
            
        items = resp.get('Items', [])
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'orders': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Query Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

def update_vicinity(order_id, event):
    body = json.loads(event.get('body', '{}'))
    vicinity_event = body.get('event')
    
    # Fetch current state
    if not orders_table:
         return {'statusCode': 500}
         
    resp = orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')
    
    if not session:
        raise NotFoundError()
    
    now = int(time.time())
    
    # --- Capacity-gated path for 5_MIN_OUT ---
    # When a customer is 5 minutes out, check if the restaurant has capacity.
    # Other events (PARKING, AT_DOOR, EXIT_VICINITY) bypass capacity checks.
    if vicinity_event == '5_MIN_OUT' and capacity_table:
        destination_id = session.get('destination_id', session.get('restaurant_id'))
        cap_result = capacity.check_and_reserve_for_arrival(
            capacity_table=capacity_table,
            config_table=config_table,
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
        orders_table.update_item(**kwargs)
        
    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=decimal_default)
    }

def add_tip(order_id, event):
    # Minimal implementation for demo
    if not orders_table:
        return {'statusCode': 500}
        
    body = json.loads(event.get('body', '{}'))
    tip_cents = body.get('tip_cents', 0)
    
    orders_table.update_item(
        Key={'order_id': order_id},
        UpdateExpression="SET tip_cents = :t",
        ExpressionAttributeValues={':t': tip_cents}
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({'success': True})
    }


def _release_capacity_slot(session: Dict[str, Any]) -> None:
    """
    Release a capacity slot if one was reserved for this session.
    Safe to call even if no slot was reserved (no-ops gracefully).
    """
    if not capacity_table:
        return

    window_start = session.get('capacity_window_start')
    if window_start is None:
        return  # No capacity slot was ever reserved

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    capacity.release_slot(
        table=capacity_table,
        destination_id=destination_id,
        window_start=int(window_start),
    )

def update_order_status(order_id, event):
    if not orders_table:
        return {'statusCode': 500}
        
    body = json.loads(event.get('body', '{}'))
    new_status = body.get('status')
    
    if not new_status:
        return {'statusCode': 400, 'body': json.dumps({'error': 'Missing status'})}

    # Fetch session first so we can release capacity on completion
    resp = orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')
    if not session:
        raise NotFoundError()

    try:
        orders_table.update_item(
            Key={'order_id': order_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': new_status},
            ConditionExpression="attribute_exists(order_id)"
        )

        # Release capacity slot when order is completed
        if new_status in ('COMPLETED', models.STATUS_COMPLETED):
            _release_capacity_slot(session)

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'status': new_status})
        }
    except Exception as e:
        print(f"Update Status Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def cancel_order(order_id):
    if not orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    resp = orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    if not session:
        raise NotFoundError()

    now = int(time.time())
    plan = engine.decide_cancel(session, now)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        orders_table.update_item(**kwargs)

    # Release capacity slot if one was reserved
    _release_capacity_slot(session)

    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=decimal_default)
    }


def ack_order(order_id, restaurant_id):
    if not orders_table:
        return {'statusCode': 500, 'body': 'DB not configured'}

    resp = orders_table.get_item(Key={'order_id': order_id})
    session = resp.get('Item')

    if not session:
        raise NotFoundError()

    now = int(time.time())
    plan = engine.decide_ack_upgrade(session, restaurant_id, now)

    kwargs = build_update_item_kwargs(order_id, plan)
    if kwargs:
        orders_table.update_item(**kwargs)

    return {
        'statusCode': 200,
        'body': json.dumps(plan.response, default=decimal_default)
    }
