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
from typing import Dict, Any, List
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from pos_mapper import pos_order_to_session, session_to_pos_order, pos_menu_to_resources

dynamodb = boto3.resource('dynamodb')

PAYMENT_MODE_AT_RESTAURANT = "PAY_AT_RESTAURANT"
POS_MENU_SYNC_ENABLED = os.environ.get("POS_MENU_SYNC_ENABLED", "false").lower() == "true"

STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_DESTINATION"
STATUS_WAITING = "WAITING_FOR_CAPACITY"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_READY = "READY"
STATUS_FULFILLING = "FULFILLING"
STATUS_COMPLETED = "COMPLETED"

CHAIN_TRANSITIONS = {
    STATUS_SENT: (STATUS_IN_PROGRESS,),
    STATUS_IN_PROGRESS: (STATUS_READY,),
    STATUS_READY: (STATUS_FULFILLING,),
    STATUS_FULFILLING: (STATUS_COMPLETED,),
}

# Table references (cross-service, passed via environment)
ORDERS_TABLE = os.environ.get('ORDERS_TABLE', '')
MENUS_TABLE = os.environ.get('MENUS_TABLE', '')
WEBHOOK_LOGS_TABLE = os.environ.get('POS_WEBHOOK_LOGS_TABLE', '')
CAPACITY_TABLE = os.environ.get('CAPACITY_TABLE', '')

for _name, _val in [
    ('ORDERS_TABLE', ORDERS_TABLE),
    ('MENUS_TABLE', MENUS_TABLE),
    ('POS_WEBHOOK_LOGS_TABLE', WEBHOOK_LOGS_TABLE),
    ('CAPACITY_TABLE', CAPACITY_TABLE),
]:
    if not _val:
        print(f"WARN: {_name} env var not set — related operations will be no-ops")

orders_table = dynamodb.Table(ORDERS_TABLE) if ORDERS_TABLE else None
menus_table = dynamodb.Table(MENUS_TABLE) if MENUS_TABLE else None
webhook_logs_table = dynamodb.Table(WEBHOOK_LOGS_TABLE) if WEBHOOK_LOGS_TABLE else None
capacity_table = dynamodb.Table(CAPACITY_TABLE) if CAPACITY_TABLE else None


def _fetch_order(order_id: str):
    if not orders_table:
        return None
    if not order_id:
        return None
    resp = orders_table.get_item(Key={'order_id': order_id})
    return resp.get('Item')


def _status_map() -> Dict[str, str]:
    return {
        'PREPARING': STATUS_IN_PROGRESS,
        'READY': STATUS_READY,
        'PICKED_UP': STATUS_FULFILLING,
        'COMPLETED': STATUS_COMPLETED,
        # Also accept Arrive-native statuses
        STATUS_IN_PROGRESS: STATUS_IN_PROGRESS,
        STATUS_FULFILLING: STATUS_FULFILLING,
        STATUS_PENDING: STATUS_PENDING,
        STATUS_SENT: STATUS_SENT,
        STATUS_READY: STATUS_READY,
        STATUS_COMPLETED: STATUS_COMPLETED,
    }


def _validate_transition(current_status: str, target_status: str) -> str:
    current = str(current_status or '')
    target = str(target_status or '')

    if not target:
        return "Missing status"

    # Idempotent updates are accepted.
    if current == target:
        return ""

    if target == STATUS_SENT:
        if current in (STATUS_PENDING, STATUS_WAITING):
            return ""
        return f"Invalid transition {current} -> {target}"

    allowed_next = CHAIN_TRANSITIONS.get(current, ())
    if target in allowed_next:
        return ""

    return f"Invalid transition {current} -> {target}"


def _timestamp_fields_for_status(target_status: str, now: int) -> Dict[str, Any]:
    fields: Dict[str, Any] = {'updated_at': now}
    if target_status == STATUS_IN_PROGRESS:
        fields['started_at'] = now
    elif target_status == STATUS_READY:
        fields['ready_at'] = now
    elif target_status == STATUS_FULFILLING:
        fields['fulfilling_at'] = now
    elif target_status == STATUS_COMPLETED:
        fields['completed_at'] = now
    elif target_status == STATUS_SENT:
        fields['sent_at'] = now
        fields['vicinity'] = True
        fields['receipt_mode'] = 'HARD'
    return fields


def _build_set_expression(status: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    expr_names = {'#s': 'status'}
    expr_values = {':status': status}
    assignments = ['#s = :status']
    idx = 0
    for key, value in fields.items():
        idx += 1
        name_ref = f"#f{idx}"
        val_ref = f":f{idx}"
        expr_names[name_ref] = key
        expr_values[val_ref] = value
        assignments.append(f"{name_ref} = {val_ref}")

    return {
        'UpdateExpression': "SET " + ", ".join(assignments),
        'ExpressionAttributeNames': expr_names,
        'ExpressionAttributeValues': expr_values,
    }


def _update_order_with_guard(
    order_id: str,
    restaurant_id: str,
    current_status: str,
    target_status: str,
    extra_fields: Dict[str, Any],
) -> bool:
    if not orders_table:
        return True

    request = _build_set_expression(target_status, extra_fields)
    request['Key'] = {'order_id': order_id}
    request['ConditionExpression'] = 'restaurant_id = :rid AND #s = :allowed'
    request['ExpressionAttributeValues'].update({
        ':rid': restaurant_id,
        ':allowed': current_status,
    })

    orders_table.update_item(**request)
    return True


def _release_capacity_slot(session: Dict[str, Any]) -> None:
    if not capacity_table:
        return

    window_start = session.get('capacity_window_start')
    if window_start is None:
        return

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    if not destination_id:
        return

    try:
        capacity_table.update_item(
            Key={
                'restaurant_id': destination_id,
                'window_start': int(window_start),
            },
            UpdateExpression="SET current_count = current_count - :one",
            ConditionExpression=Attr("current_count").gt(0),
            ExpressionAttributeValues={":one": 1},
        )
    except Exception:
        # Best effort: slot may already be released or row expired.
        return


def handle_create_order(body: Dict[str, Any], key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS → Arrive: Create a new order from POS data.
    
    The POS pushes an order that should be tracked by Arrive's timing engine.
    """
    pos_system = key_record.get('pos_system', 'generic')
    restaurant_id = key_record['restaurant_id']

    requested_payment_mode = body.get("payment_mode")
    if requested_payment_mode and requested_payment_mode != PAYMENT_MODE_AT_RESTAURANT:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Only PAY_AT_RESTAURANT is supported"}),
        }
    
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
        'status': STATUS_PENDING,
        'arrival_status': None,
        'payment_mode': PAYMENT_MODE_AT_RESTAURANT,
        'pos_order_ref': session_data.get('pos_order_ref', ''),
        'pos_system': pos_system,
        'total_cents': total_cents,
        'work_units_total': work_units,
        'arrive_fee_cents': arrive_fee,
        'created_at': now,
        'expires_at': now + 3600,
        'ttl': now + (90 * 24 * 60 * 60), # 90 days retention
        'vicinity': False,
    }

    if orders_table:
        orders_table.put_item(Item=order)

    return {
        'statusCode': 201,
        'body': json.dumps({
            'arrive_order_id': order_id,
            'pos_order_ref': session_data.get('pos_order_ref', ''),
            'status': STATUS_PENDING,
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

    # Query using GSI_RestaurantStatus (efficient lookup)
    key_condition = 'restaurant_id = :rid'
    expr_values = {':rid': restaurant_id}
    expr_names = {}
    
    if status_filter:
        key_condition += ' AND #s = :status'
        expr_values[':status'] = status_filter
        expr_names['#s'] = 'status'
    
    query_kwargs = {
        'IndexName': 'GSI_RestaurantStatus',
        'KeyConditionExpression': key_condition,
        'ExpressionAttributeValues': expr_values
    }
    if expr_names:
        query_kwargs['ExpressionAttributeNames'] = expr_names

    response = orders_table.query(**query_kwargs)

    orders = response.get('Items', [])

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

    arrive_status = _status_map().get(new_status)
    if not arrive_status:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown status: {new_status}', 'valid_statuses': list(_status_map().keys())})
        }

    if orders_table:
        session = _fetch_order(order_id)
        if not session:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Order not found'})}
        if session.get('restaurant_id') != restaurant_id:
            return {'statusCode': 403, 'body': json.dumps({'error': 'Order does not belong to this restaurant'})}

        current_status = str(session.get('status') or '')
        transition_error = _validate_transition(current_status, arrive_status)
        if transition_error:
            return {'statusCode': 409, 'body': json.dumps({'error': transition_error})}

        if current_status == arrive_status:
            if arrive_status == STATUS_COMPLETED:
                _release_capacity_slot(session)
            return {
                'statusCode': 200,
                'body': json.dumps({'order_id': order_id, 'status': arrive_status, 'idempotent': True})
            }

        try:
            now = int(time.time())
            _update_order_with_guard(
                order_id=order_id,
                restaurant_id=restaurant_id,
                current_status=current_status,
                target_status=arrive_status,
                extra_fields=_timestamp_fields_for_status(arrive_status, now),
            )
        except (dynamodb.meta.client.exceptions.ConditionalCheckFailedException, ClientError):
            return {'statusCode': 409, 'body': json.dumps({'error': 'Order changed concurrently; retry'})}

        if arrive_status == STATUS_COMPLETED:
            _release_capacity_slot(session)

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
        session = _fetch_order(order_id)
        if not session:
            return {'statusCode': 404, 'body': json.dumps({'error': 'Order not found'})}
        if session.get('restaurant_id') != restaurant_id:
            return {'statusCode': 403, 'body': json.dumps({'error': 'Order does not belong to this restaurant'})}

        current_status = str(session.get('status') or '')
        transition_error = _validate_transition(current_status, STATUS_SENT)
        if transition_error:
            return {'statusCode': 409, 'body': json.dumps({'error': transition_error})}

        if current_status == STATUS_SENT:
            return {
                'statusCode': 200,
                'body': json.dumps({'order_id': order_id, 'status': STATUS_SENT, 'fired': True, 'idempotent': True})
            }

        try:
            now = int(time.time())
            _update_order_with_guard(
                order_id=order_id,
                restaurant_id=restaurant_id,
                current_status=current_status,
                target_status=STATUS_SENT,
                extra_fields=_timestamp_fields_for_status(STATUS_SENT, now),
            )
        except (dynamodb.meta.client.exceptions.ConditionalCheckFailedException, ClientError):
            return {'statusCode': 409, 'body': json.dumps({'error': 'Order not in a fireable state or changed concurrently'})}

    return {
        'statusCode': 200,
        'body': json.dumps({'order_id': order_id, 'status': STATUS_SENT, 'fired': True})
    }


def handle_get_menu(key_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    POS ← Arrive: Get current menu for the restaurant.
    """
    restaurant_id = key_record['restaurant_id']

    if not menus_table:
        return {'statusCode': 200, 'body': json.dumps({'menu': [], 'restaurant_id': restaurant_id})}

    try:
        response = menus_table.get_item(
            Key={'restaurant_id': restaurant_id, 'menu_version': 'latest'}
        )
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
    """
    if not POS_MENU_SYNC_ENABLED:
        return {
            "statusCode": 409,
            "body": json.dumps(
                {"error": "POS menu sync is disabled; use restaurant admin CSV ingestion"}
            ),
        }

    restaurant_id = key_record['restaurant_id']
    pos_system = key_record.get('pos_system', 'generic')

    pos_items = body.get('items', [])
    if not pos_items:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'items must be a non-empty list'}),
        }
    resources = pos_menu_to_resources(pos_items, pos_system)

    if menus_table:
        menus_table.put_item(Item={
            'restaurant_id': restaurant_id,
            'menu_version': 'latest',
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
