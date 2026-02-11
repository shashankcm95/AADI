"""
POS Integration Service - Lambda Entry Point

Routes incoming HTTP API requests to the appropriate handler.
All routes require API key authentication via X-POS-API-Key header.
"""

import json
from auth import authenticate_request, require_permission
from handlers import (
    handle_create_order,
    handle_list_orders,
    handle_update_status,
    handle_force_fire,
    handle_get_menu,
    handle_sync_menu,
    handle_webhook,
)


def lambda_handler(event, context):
    """Main entry point for POS Integration Lambda."""
    
    route_key = event.get('routeKey', '')
    path_params = event.get('pathParameters') or {}
    query_params = event.get('queryStringParameters') or {}
    
    # --- Authenticate ---
    key_record = authenticate_request(event)
    if not key_record:
        return {
            'statusCode': 401,
            'body': json.dumps({
                'error': 'Unauthorized',
                'message': 'Missing or invalid X-POS-API-Key header',
            })
        }

    # --- Route ---
    try:
        body = json.loads(event.get('body', '{}')) if event.get('body') else {}

        # POST /v1/pos/orders — Create order from POS
        if route_key == 'POST /v1/pos/orders':
            if not require_permission(key_record, 'orders:write'):
                return _forbidden('orders:write')
            return handle_create_order(body, key_record)

        # GET /v1/pos/orders — List orders
        elif route_key == 'GET /v1/pos/orders':
            if not require_permission(key_record, 'orders:read'):
                return _forbidden('orders:read')
            return handle_list_orders(key_record, query_params)

        # POST /v1/pos/orders/{order_id}/status — Update order status
        elif route_key == 'POST /v1/pos/orders/{order_id}/status':
            if not require_permission(key_record, 'orders:write'):
                return _forbidden('orders:write')
            order_id = path_params.get('order_id')
            return handle_update_status(order_id, body, key_record)

        # POST /v1/pos/orders/{order_id}/fire — Force fire order
        elif route_key == 'POST /v1/pos/orders/{order_id}/fire':
            if not require_permission(key_record, 'orders:write'):
                return _forbidden('orders:write')
            order_id = path_params.get('order_id')
            return handle_force_fire(order_id, key_record)

        # GET /v1/pos/menu — Get menu
        elif route_key == 'GET /v1/pos/menu':
            if not require_permission(key_record, 'menu:read'):
                return _forbidden('menu:read')
            return handle_get_menu(key_record)

        # POST /v1/pos/menu/sync — Sync menu from POS
        elif route_key == 'POST /v1/pos/menu/sync':
            if not require_permission(key_record, 'menu:write'):
                return _forbidden('menu:write')
            return handle_sync_menu(body, key_record)

        # POST /v1/pos/webhook — Generic webhook
        elif route_key == 'POST /v1/pos/webhook':
            return handle_webhook(body, key_record)

        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not Found', 'route': route_key})
            }

    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        print(f"POS Integration Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal Server Error'})
        }


def _forbidden(permission: str) -> dict:
    return {
        'statusCode': 403,
        'body': json.dumps({
            'error': 'Forbidden',
            'message': f'API key does not have required permission: {permission}',
        })
    }
