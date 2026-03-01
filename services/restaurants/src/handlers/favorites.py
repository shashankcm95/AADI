"""Customer favorites handlers."""
import json
import time
from boto3.dynamodb.conditions import Key

from utils import (
    CORS_HEADERS, decimal_default, _require_customer, make_response,
    favorites_table, restaurants_table,
)


def list_favorites(event):
    """List favorite restaurants for the authenticated customer."""
    if not favorites_table:
        return make_response(500, {'error': 'Favorites table not configured'})

    customer_id, err = _require_customer(event)
    if err:
        return err

    try:
        resp = favorites_table.query(
            KeyConditionExpression=Key('customer_id').eq(customer_id)
        )
        items = resp.get('Items', [])

        return make_response(200, {'favorites': items})
    except Exception as e:
        print(f"List Favorites Error: {e}")
        return make_response(500, {'error': 'Internal server error'})


def add_favorite(event, restaurant_id):
    """Add one restaurant to the authenticated customer's favorites."""
    if not favorites_table:
        return make_response(500, {'error': 'Favorites table not configured'})

    if not restaurant_id:
        return make_response(400, {'error': 'restaurant_id is required'})

    customer_id, err = _require_customer(event)
    if err:
        return err

    try:
        if restaurants_table:
            restaurant = restaurants_table.get_item(Key={'restaurant_id': restaurant_id}).get('Item')
            if not restaurant:
                return make_response(404, {'error': 'Restaurant not found'})

        item = {
            'customer_id': customer_id,
            'restaurant_id': restaurant_id,
            'created_at': int(time.time()),
        }
        favorites_table.put_item(Item=item)

        return make_response(200, {'favorite': item})
    except Exception as e:
        print(f"Add Favorite Error: {e}")
        return make_response(500, {'error': 'Internal server error'})


def remove_favorite(event, restaurant_id):
    """Remove one restaurant from the authenticated customer's favorites."""
    if not favorites_table:
        return make_response(500, {'error': 'Favorites table not configured'})

    if not restaurant_id:
        return make_response(400, {'error': 'restaurant_id is required'})

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
        return make_response(200, {'removed': True})
    except Exception as e:
        print(f"Remove Favorite Error: {e}")
        return make_response(500, {'error': 'Internal server error'})
