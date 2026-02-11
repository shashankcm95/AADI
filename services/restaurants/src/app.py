import json
import os
import boto3
import traceback
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB resources
dynamodb = boto3.resource('dynamodb')
RESTAURANTS_TABLE = os.environ.get('RESTAURANTS_TABLE')
MENUS_TABLE = os.environ.get('MENUS_TABLE')
RESTAURANT_CONFIG_TABLE = os.environ.get('RESTAURANT_CONFIG_TABLE')

restaurants_table = dynamodb.Table(RESTAURANTS_TABLE) if RESTAURANTS_TABLE else None
menus_table = dynamodb.Table(MENUS_TABLE) if MENUS_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
}


def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")
    route_key = event.get('routeKey')
    path_params = event.get('pathParameters') or {}

    try:
        if route_key == 'GET /v1/restaurants/health':
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps({'status': 'healthy'})
            }

        if route_key == 'GET /v1/restaurants':
            return list_restaurants()

        elif route_key == 'GET /v1/restaurants/{restaurant_id}/menu':
            return get_menu(path_params.get('restaurant_id'))

        return {
            'statusCode': 404,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Not Found'})
        }

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Internal server error'})}


def list_restaurants():
    """List all restaurants from DynamoDB."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurants table not configured'})}

    try:
        resp = restaurants_table.scan(
            FilterExpression='active = :a',
            ExpressionAttributeValues={':a': True}
        )
        items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'restaurants': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Scan Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def get_menu(restaurant_id):
    """Get the active menu for a restaurant from DynamoDB."""
    if not menus_table:
        return {'statusCode': 200, 'body': json.dumps({'menu': {'items': []}})}

    try:
        # First, get the active menu version from config
        active_version = 'v1'  # default
        if config_table:
            config_resp = config_table.get_item(Key={'restaurant_id': restaurant_id})
            config = config_resp.get('Item', {})
            active_version = config.get('active_menu_version', 'v1')

        # Now get the menu for that version
        resp = menus_table.get_item(
            Key={'restaurant_id': restaurant_id, 'menu_version': active_version}
        )
        item = resp.get('Item', {})
        menu = item.get('menu', {'items': []})

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'menu': menu}, default=decimal_default)
        }
    except Exception as e:
        print(f"Menu Error: {e}")
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({'menu': {'items': []}})}
