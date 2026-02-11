"""
POS Integration Handlers

Business logic for each POS endpoint. All handlers receive:
- body: parsed request body
- key_record: authenticated API key record with restaurant_id
- query_params: URL query parameters
"""

import json
import os
import time
import uuid
import boto3
from typing import Dict, Any, Optional, List
from pos_mapper import pos_order_to_session, session_to_pos_order, pos_menu_to_resources

dynamodb = boto3.resource('dynamodb')

# Table references (cross-service, passed via environment)
ORDERS_TABLE = os.environ.get('ORDERS_TABLE', '')
MENUS_TABLE = os.environ.get('MENUS_TABLE', '')
WEBHOOK_LOGS_TABLE = os.environ.get('POS_WEBHOOK_LOGS_TABLE', '')

orders_table = dynamodb.Table(ORDERS_TABLE) if ORDERS_TABLE else None
menus_table = dynamodb.Table(MENUS_TABLE) if MENUS_TABLE else None
webhook_logs_table = dynamodb.Table(WEBHOOK_LOGS_TABLE) if WEBHOOK_LOGS_TABLE else None


def handle_create_order(body: Dict[str, Any], key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Create a new order from POS data.
    
    The POS pushes an order when a customer has prepaid or placed an order
    that should be tracked by Arrive's timing engine.
    """
    pos_system = key_record.get('pos_system', 'generic')
    restaurant_id = key_record['restaurant_id']
    
    # Translate POS format → Arrive format
    session_data = pos_order_to_session(body, pos_system)
    
    # Override restaurant_id from API key (security: POS can only create for their own restaurant)
    session_data['restaurant_id'] = restaurant_id
    
    now = int(time.time())
    order_id = f"ord_pos_{uuid.uuid4().hex[:12]}"
    
    # Calculate totals
    total_cents = 0
    work_units = 0
    for item in session_data.get('items', []):
        qty = item.get('qty', 1)
        total_cents += item.get('price_cents', 0) * qty
        work_units += item.get('work_units', 1) * qty

    # Calculate Arrive fee
    fee_percent = 2.0
    arrive_fee = int(total_cents * fee_percent / 100)

    order = {
        'order_id': order_id,
        'session_id': order_id,
        'destination_id': restaurant_id,
        'restaurant_id': restaurant_id,
        'customer_name': session_data.get('customer_name', 'Guest'),
        'items': session_data.get('items', []),
        'status': 'PENDING_NOT_SENT',
        'arrival_status': None,
        'payment_mode': body.get('payment_mode', 'PAY_AT_RESTAURANT'),
        'pos_order_ref': session_data.get('pos_order_ref', ''),
        'pos_system': pos_system,
        'total_cents': total_cents,
        'work_units_total': work_units,
        'arrive_fee_cents': arrive_fee,
        'created_at': now,
        'expires_at': now + 3600,
        'vicinity': False,
        'tip_cents': 0,
    }

    if orders_table:
        orders_table.put_item(Item=order)

    return {
        'statusCode': 201,
        'body': json.dumps({
            'arrive_order_id': order_id,
            'pos_order_ref': session_data.get('pos_order_ref', ''),
            'status': 'PENDING_NOT_SENT',
            'arrive_fee_cents': arrive_fee,
        })
    }


def handle_list_orders(key_record: Dict[str, Any], query_params: Dict[str, str]) -> Dict[str, Any]:
    """
    POS ← Arrive: List orders for the restaurant.
    
    POS can poll this to see all active Arrive orders.
    """
    restaurant_id = key_record['restaurant_id']
    status_filter = query_params.get('status')

    if not orders_table:
        return {'statusCode': 200, 'body': json.dumps({'orders': []})}

    # Scan for restaurant's orders (in production, use GSI on restaurant_id)
    response = orders_table.scan(
        FilterExpression='restaurant_id = :rid',
        ExpressionAttributeValues={':rid': restaurant_id}
    )
    
    orders = response.get('Items', [])
    
    if status_filter:
        orders = [o for o in orders if o.get('status') == status_filter]

    # Convert to POS-friendly format
    pos_orders = [session_to_pos_order(o) for o in orders]

    return {
        'statusCode': 200,
        'body': json.dumps({'orders': pos_orders, 'count': len(pos_orders)})
    }


def handle_update_status(order_id: str, body: Dict[str, Any], key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Update an order's status.
    
    Maps POS status events to Arrive's state machine.
    """
    restaurant_id = key_record['restaurant_id']
    new_status = body.get('status')
    
    status_map = {
        'PREPARING': 'IN_PROGRESS',
        'READY': 'READY',
        'PICKED_UP': 'FULFILLING',
        'COMPLETED': 'COMPLETED',
        'CANCELLED': 'CANCELLED',
        # Also accept Arrive-native statuses
        'IN_PROGRESS': 'IN_PROGRESS',
        'FULFILLING': 'FULFILLING',
        'PENDING_NOT_SENT': 'PENDING_NOT_SENT',
        'SENT_TO_DESTINATION': 'SENT_TO_DESTINATION',
    }

    arrive_status = status_map.get(new_status)
    if not arrive_status:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown status: {new_status}', 'valid_statuses': list(status_map.keys())})
        }

    if orders_table:
        now = int(time.time())
        update_expr = 'SET #s = :status, updated_at = :now'
        expr_values = {':status': arrive_status, ':now': now, ':rid': restaurant_id}
        expr_names = {'#s': 'status'}
        
        # Add completed_at for terminal states
        if arrive_status in ('COMPLETED', 'CANCELLED'):
            update_expr += ', completed_at = :now'

        try:
            orders_table.update_item(
                Key={'order_id': order_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names,
                ConditionExpression='restaurant_id = :rid',
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return {'statusCode': 403, 'body': json.dumps({'error': 'Order does not belong to this restaurant'})}

    return {
        'statusCode': 200,
        'body': json.dumps({'order_id': order_id, 'status': arrive_status})
    }


def handle_force_fire(order_id: str, key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Force-fire an order.
    
    Manually triggers the kitchen to start preparing, regardless of GPS state.
    This is the staff-side equivalent of the customer's "I'm Here" button.
    """
    restaurant_id = key_record['restaurant_id']

    if orders_table:
        now = int(time.time())
        try:
            orders_table.update_item(
                Key={'order_id': order_id},
                UpdateExpression='SET #s = :status, sent_at = :now, vicinity = :v, receipt_mode = :rm',
                ExpressionAttributeValues={
                    ':status': 'SENT_TO_DESTINATION',
                    ':now': now,
                    ':v': True,
                    ':rm': 'HARD',
                    ':rid': restaurant_id,
                    ':allowed': 'PENDING_NOT_SENT',
                    ':allowed2': 'WAITING',
                },
                ExpressionAttributeNames={'#s': 'status'},
                ConditionExpression='restaurant_id = :rid AND (#s = :allowed OR #s = :allowed2)',
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return {'statusCode': 409, 'body': json.dumps({'error': 'Order not in a fireable state or wrong restaurant'})}

    return {
        'statusCode': 200,
        'body': json.dumps({'order_id': order_id, 'status': 'SENT_TO_DESTINATION', 'fired': True})
    }


def handle_get_menu(key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS ← Arrive: Get current menu for the restaurant.
    """
    restaurant_id = key_record['restaurant_id']

    if not menus_table:
        return {'statusCode': 200, 'body': json.dumps({'menu': [], 'restaurant_id': restaurant_id})}

    try:
        response = menus_table.get_item(Key={'restaurant_id': restaurant_id})
        item = response.get('Item', {})
        menu_items = item.get('items', [])
    except Exception:
        menu_items = []

    return {
        'statusCode': 200,
        'body': json.dumps({'menu': menu_items, 'restaurant_id': restaurant_id})
    }


def handle_sync_menu(body: Dict[str, Any], key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Push menu updates from POS to Arrive.
    
    The POS is the source of truth for the menu.
    """
    restaurant_id = key_record['restaurant_id']
    pos_system = key_record.get('pos_system', 'generic')
    
    pos_items = body.get('items', [])
    resources = pos_menu_to_resources(pos_items, pos_system)

    if menus_table:
        menus_table.put_item(Item={
            'restaurant_id': restaurant_id,
            'items': resources,
            'synced_at': int(time.time()),
            'pos_system': pos_system,
        })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'synced': len(resources),
            'restaurant_id': restaurant_id,
        })
    }


def handle_webhook(body: Dict[str, Any], key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Generic webhook endpoint.
    
    Handles various POS event types (order.created, order.updated, etc.)
    with idempotency via webhook_id dedup.
    """
    webhook_id = body.get('webhook_id', body.get('event_id', f"wh_{uuid.uuid4().hex[:12]}"))
    event_type = body.get('event_type', body.get('type', 'unknown'))

    # Idempotency check
    if webhook_logs_table:
        try:
            webhook_logs_table.put_item(
                Item={
                    'webhook_id': webhook_id,
                    'event_type': event_type,
                    'restaurant_id': key_record['restaurant_id'],
                    'received_at': int(time.time()),
                    'ttl': int(time.time()) + 86400,  # 24h TTL
                    'payload': json.dumps(body),
                },
                ConditionExpression='attribute_not_exists(webhook_id)',
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Already processed — idempotent return
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'already_processed', 'webhook_id': webhook_id})
            }

    # Route webhook by event type
    if event_type in ('order.created', 'order.placed'):
        return handle_create_order(body.get('data', body), key_record)
    elif event_type in ('order.updated', 'order.status_changed'):
        order_id = body.get('data', {}).get('order_id', '')
        return handle_update_status(order_id, body.get('data', body), key_record)
    else:
        # Log but don't fail on unknown events
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'acknowledged', 'event_type': event_type, 'webhook_id': webhook_id})
        }
