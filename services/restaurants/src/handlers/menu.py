"""Menu handlers."""
import json
import uuid
import time
from decimal import Decimal

from utils import (
    CORS_HEADERS, decimal_default, get_user_claims, make_response,
    menus_table,
)
from shared.logger import get_logger

menu_log = get_logger("restaurants.menu")


def get_menu(restaurant_id):
    """Get the active menu for a restaurant from DynamoDB."""
    if not menus_table:
        return make_response(200, {'menu': {'items': []}})

    try:
        version = 'latest'

        resp = menus_table.get_item(
            Key={'restaurant_id': restaurant_id, 'menu_version': version}
        )
        item = resp.get('Item', {})
        items = item.get('items', [])

        return make_response(200, {'items': items})
    except Exception as e:
        print(f"Menu Error: {e}")
        return make_response(200, {'menu': {'items': []}})


def update_menu(event, restaurant_id):
    """Update (Overwrite) the menu for a restaurant."""
    if not menus_table:
        return make_response(500, {'error': 'Menus table not configured'})

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return make_response(403, {'error': 'Access denied'})

    try:
        body = json.loads(event.get('body', '{}'))
        items = body.get('items', [])

        print(f"Received {len(items)} items for restaurant {restaurant_id}")
        if len(items) > 0:
            print(f"Sample Item: {items[0]}")

        if not isinstance(items, list):
            return make_response(400, {'error': 'Payload must contain an "items" list'})

        cleaned_items = []
        for item in items:
            if not item.get('name') or item.get('price') is None:
                print(f"Skipping item due to missing fields: {item}")
                continue

            try:
                price_str = str(item['price']).replace('$', '').replace(',', '').strip()
                price = Decimal(price_str)
                item['price'] = price
                item['price_cents'] = int(price * 100)
            except Exception as e:
                print(f"Skipping key {item.get('name')} due to invalid price: {item.get('price')} - Error: {e}")
                continue

            if not item.get('id'):
                item['id'] = str(uuid.uuid4())

            cleaned_items.append(item)

        print(f"Cleaned items count: {len(cleaned_items)}")

        menu_item = {
            'restaurant_id': restaurant_id,
            'menu_version': 'latest',
            'items': cleaned_items,
            'updated_at': int(time.time()),
            'updated_by': claims.get('username', 'unknown')
        }

        menus_table.put_item(Item=menu_item)

        return make_response(200, {'message': 'Menu updated successfully', 'count': len(cleaned_items)})

    except Exception as e:
        menu_log.error("menu_update_failed", extra={"restaurant_id": restaurant_id, "detail": str(e)}, exc_info=True)
        return make_response(500, {'error': 'Internal server error'})
