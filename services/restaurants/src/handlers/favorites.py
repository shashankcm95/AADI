"""Customer favorites handlers."""
import json
import time
from boto3.dynamodb.conditions import Key

from utils import (
    CORS_HEADERS, decimal_default, _require_customer,
    favorites_table, restaurants_table,
)


def list_favorites(event):
    """List favorite restaurants for the authenticated customer."""
    if not favorites_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Favorites table not configured'})}

    customer_id, err = _require_customer(event)
    if err:
        return err

    try:
        resp = favorites_table.query(
            KeyConditionExpression=Key('customer_id').eq(customer_id)
        )
        items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'favorites': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"List Favorites Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def add_favorite(event, restaurant_id):
    """Add one restaurant to the authenticated customer's favorites."""
    if not favorites_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Favorites table not configured'})}

    if not restaurant_id:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'restaurant_id is required'})}

    customer_id, err = _require_customer(event)
    if err:
        return err

    try:
        if restaurants_table:
            restaurant = restaurants_table.get_item(Key={'restaurant_id': restaurant_id}).get('Item')
            if not restaurant:
                return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant not found'})}

        item = {
            'customer_id': customer_id,
            'restaurant_id': restaurant_id,
            'created_at': int(time.time()),
        }
        favorites_table.put_item(Item=item)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'favorite': item}, default=decimal_default)
        }
    except Exception as e:
        print(f"Add Favorite Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def remove_favorite(event, restaurant_id):
    """Remove one restaurant from the authenticated customer's favorites."""
    if not favorites_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Favorites table not configured'})}

    if not restaurant_id:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'restaurant_id is required'})}

    customer_id, err = _require_customer(event)
    if err:
        return err

    try:
        favorites_table.delete_item(
            Key={
                'customer_id': customer_id,
                'restaurant_id': restaurant_id
            }
        )
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'removed': True})
        }
    except Exception as e:
        print(f"Remove Favorite Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}
