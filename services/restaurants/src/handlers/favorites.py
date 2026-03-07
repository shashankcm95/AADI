"""Customer favorites handlers."""
import time
from boto3.dynamodb.conditions import Key

from shared.logger import get_logger
from utils import (
    _require_customer, make_response,
    favorites_table, restaurants_table,
)

logger = get_logger("restaurants.favorites")


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
        logger.error("list_favorites_failed", extra={"error": str(e)})
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
        logger.error("add_favorite_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
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
        logger.error("remove_favorite_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
        return make_response(500, {'error': 'Internal server error'})
