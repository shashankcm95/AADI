"""
Orders Service — Lambda Entry Point

Slim router that dispatches API Gateway events to handler modules.
All business logic lives in handlers/customer.py and handlers/restaurant.py.
"""
import json
import traceback

import db
from handlers.customer import (
    create_order,
    get_order,
    list_customer_orders,
    update_vicinity,
    cancel_order,
)
from handlers.restaurant import (
    list_restaurant_orders,
    ack_order,
    update_order_status,
)
from errors import NotFoundError, InvalidStateError, ValidationError, ExpiredError


CUSTOMER_ROUTES = {
    'POST /v1/orders',
    'GET /v1/orders/{order_id}',
    'GET /v1/orders',
    'POST /v1/orders/{order_id}/vicinity',
    'POST /v1/orders/{order_id}/cancel',
}

RESTAURANT_ROUTES = {
    'GET /v1/restaurants/{restaurant_id}/orders',
    'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack',
    'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
}


def lambda_handler(event, context):
    """
    Entry point for Orders Service Lambda
    """
    print(f"Event: {json.dumps(event)}")

    # Determine routing
    route_key = event.get('routeKey')
    print(f"DEBUG_ROUTE_KEY: {route_key}")
    path_params = event.get('pathParameters', {})

    try:
        known_routes = CUSTOMER_ROUTES | RESTAURANT_ROUTES
        claims = db.get_auth_claims(event)
        role = db.get_user_role(event)
        assigned_restaurant_id = db.get_assigned_restaurant_id(event)
        customer_id = claims.get('sub')

        if route_key in known_routes and not claims:
            return db.make_response(401, {'error': 'Unauthorized'})

        if route_key in CUSTOMER_ROUTES:
            if not customer_id:
                return db.make_response(401, {'error': 'Unauthorized'})
            if role != 'customer':
                return db.make_response(403, {'error': 'Access denied'})

        if route_key in RESTAURANT_ROUTES:
            if role not in ('admin', 'restaurant_admin'):
                return db.make_response(403, {'error': 'Access denied'})
            if role == 'restaurant_admin':
                requested_restaurant_id = path_params.get('restaurant_id')
                if not requested_restaurant_id or requested_restaurant_id != assigned_restaurant_id:
                    return db.make_response(403, {'error': 'Access denied'})

        if route_key == 'POST /v1/orders':
            return create_order(event)

        elif route_key == 'GET /v1/orders/{order_id}':
            return get_order(path_params.get('order_id'), customer_id)

        elif route_key == 'GET /v1/orders':
            return list_customer_orders(event)

        elif route_key == 'POST /v1/orders/{order_id}/vicinity':
            return update_vicinity(path_params.get('order_id'), event, customer_id)

        elif route_key == 'POST /v1/orders/{order_id}/cancel':
            return cancel_order(path_params.get('order_id'), customer_id)

        elif route_key == 'GET /v1/restaurants/{restaurant_id}/orders':
            return list_restaurant_orders(path_params.get('restaurant_id'), event)

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack':
            return ack_order(path_params.get('order_id'), path_params.get('restaurant_id'))

        elif route_key == 'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status':
            return update_order_status(
                path_params.get('order_id'),
                path_params.get('restaurant_id'),
                event,
            )

        else:
            return db.make_response(404, {'error': 'Route not found'})

    except NotFoundError:
        return db.make_response(404, {'error': 'Not Found'})
    except InvalidStateError as e:
        return db.make_response(409, {'error': str(e)})
    except ExpiredError as e:
        return db.make_response(409, {'error': str(e)})
    except ValidationError as e:
        return db.make_response(400, {'error': str(e)})
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return db.make_response(500, {'error': 'Internal server error'})
