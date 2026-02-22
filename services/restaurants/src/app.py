"""
Restaurants Service – Lambda entry-point.

All business logic lives in the handler modules under ``handlers/``.
This file is responsible only for:
  1. Extracting the route key and path parameters
  2. Running the global inactive-restaurant gate
  3. Dispatching to the correct handler
"""
import json
import traceback

from utils import CORS_HEADERS, get_user_claims, restaurants_table

from handlers.restaurants import (
    list_restaurants, create_restaurant, update_restaurant, delete_restaurant,
)
from handlers.menu import get_menu, update_menu
from handlers.config import get_config, update_config, get_global_config, update_global_config
from handlers.favorites import list_favorites, add_favorite, remove_favorite
from handlers.images import create_image_upload_url


def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")
    route_key = event.get('routeKey')
    path_params = event.get('pathParameters') or {}

    # ── Global Access Check for Restaurant Admins ──
    claims = get_user_claims(event)
    role = claims.get('role')
    restaurant_id = claims.get('restaurant_id')

    if role == 'restaurant_admin' and restaurant_id:
        try:
            resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
            restaurant = resp.get('Item')

            if restaurant and not restaurant.get('active', False):
                allow_request = route_key == 'GET /v1/restaurants'

                if not allow_request and route_key == 'PUT /v1/restaurants/{restaurant_id}':
                    target_restaurant_id = path_params.get('restaurant_id')
                    if target_restaurant_id == restaurant_id:
                        try:
                            body = json.loads(event.get('body', '{}'))
                        except Exception:
                            body = {}
                        allow_request = body.get('active') is True

                if not allow_request:
                    print(f"Blocking access for inactive restaurant {restaurant_id} on route {route_key}")
                    return {
                        'statusCode': 403,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'Restaurant is currently inactive/on-hold. Please contact support.'})
                    }
        except Exception as e:
            print(f"Error checking restaurant status: {e}")
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Internal authorization error'})}

    # ── Route Dispatch ──
    try:
        if route_key == 'GET /v1/restaurants/health':
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps({'status': 'healthy'})
            }

        if route_key == 'GET /v1/restaurants':
            return list_restaurants(event)

        if route_key == 'POST /v1/restaurants':
            return create_restaurant(event)

        if route_key == 'PUT /v1/restaurants/{restaurant_id}':
            return update_restaurant(event, path_params.get('restaurant_id'))

        if route_key == 'DELETE /v1/restaurants/{restaurant_id}':
            return delete_restaurant(event, path_params.get('restaurant_id'))

        elif route_key == 'GET /v1/restaurants/{restaurant_id}/menu':
            return get_menu(path_params.get('restaurant_id'))

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/menu':
            return update_menu(event, path_params.get('restaurant_id'))

        elif route_key == 'GET /v1/restaurants/{restaurant_id}/config':
            return get_config(event, path_params.get('restaurant_id'))

        elif route_key == 'PUT /v1/restaurants/{restaurant_id}/config':
            return update_config(event, path_params.get('restaurant_id'))

        elif route_key == 'GET /v1/admin/global-config':
            return get_global_config(event)

        elif route_key == 'PUT /v1/admin/global-config':
            return update_global_config(event)

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/images/upload-url':
            return create_image_upload_url(event, path_params.get('restaurant_id'))

        elif route_key == 'GET /v1/favorites':
            return list_favorites(event)

        elif route_key == 'PUT /v1/favorites/{restaurant_id}':
            return add_favorite(event, path_params.get('restaurant_id'))

        elif route_key == 'DELETE /v1/favorites/{restaurant_id}':
            return remove_favorite(event, path_params.get('restaurant_id'))

        return {
            'statusCode': 404,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Not Found'})
        }

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Internal server error'})}
