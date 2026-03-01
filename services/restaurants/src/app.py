"""
Restaurants Service – Lambda entry-point.

All business logic lives in the handler modules under ``handlers/``.
This file is responsible only for:
  1. Extracting the route key and path parameters
  2. Running the global inactive-restaurant gate
  3. Dispatching to the correct handler
"""
import json

from utils import CORS_HEADERS, get_user_claims, restaurants_table, make_response
from shared.logger import get_logger, extract_correlation_id

from handlers.restaurants import (
    get_restaurant, list_restaurants, create_restaurant, update_restaurant, delete_restaurant,
)
from handlers.menu import get_menu, update_menu
from handlers.config import get_config, update_config, get_global_config, update_global_config
from handlers.favorites import list_favorites, add_favorite, remove_favorite
from handlers.images import create_image_upload_url

log = get_logger("restaurants")


def lambda_handler(event, context):
    route_key = event.get('routeKey')
    req_log = log.bind(
        correlation_id=extract_correlation_id(event),
        route_key=route_key,
    )
    req_log.info("request_received")
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
                # Allow reading and updating own restaurant profile (name, address, images, etc.)
                # while inactive. Self-reactivation is blocked by stripping the 'active' field
                # in update_restaurant() (BL-002). All other mutation routes are blocked.
                allow_request = route_key in (
                    'GET /v1/restaurants',
                    'GET /v1/restaurants/{restaurant_id}',
                    'PUT /v1/restaurants/{restaurant_id}',
                )

                if not allow_request:
                    req_log.warning("inactive_restaurant_access_blocked", extra={
                        "restaurant_id": restaurant_id,
                        "route_key": route_key,
                    })
                    return {
                        'statusCode': 403,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'Restaurant is currently inactive/on-hold. Please contact support.'})
                    }
        except Exception as e:
            req_log.error("restaurant_status_check_failed", extra={"error": str(e)}, exc_info=True)
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

        if route_key == 'GET /v1/restaurants/{restaurant_id}':
            return get_restaurant(event, path_params.get('restaurant_id'))

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

        return make_response(404, {'error': 'Not Found'})

    except Exception as e:
        req_log.error("unhandled_exception", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        return make_response(500, {'error': 'Internal server error'})
