"""Restaurant CRUD handlers."""
import json
import base64
import re
import uuid
import time
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from shared.logger import get_logger
from utils import (
    CORS_HEADERS, decimal_default, get_user_claims, make_response,
    restaurants_table, config_table, cognito, USER_POOL_ID,
    geocode_address, _normalize_restaurant_image_keys, _decorate_restaurant_response,
    upsert_restaurant_geofences, delete_restaurant_geofences,
    DEFAULT_DISPATCH_TRIGGER_ZONE, ZONE_EVENT_MAP,
    menus_table,
)

logger = get_logger("restaurants.restaurants")


PUBLIC_REDACTED_FIELDS = frozenset({
    'contact_email',
    'restaurant_image_keys',
    'vicinity_zone',
    'is_active',
})


def _serialize_restaurant_for_role(item, role):
    """Decorate restaurant and redact internal fields for customer-facing reads."""
    response_item = _decorate_restaurant_response(item)
    if role in ('admin', 'restaurant_admin'):
        return response_item

    for field in PUBLIC_REDACTED_FIELDS:
        response_item.pop(field, None)
    return response_item


def get_restaurant(event, restaurant_id):
    """Get a single restaurant by ID."""
    if not restaurants_table:
        return make_response(500, {'error': 'Restaurants table not configured'})

    claims = get_user_claims(event)
    role = claims.get('role')

    # restaurant_admin: may only read their own assigned restaurant.
    if role == 'restaurant_admin':
        assigned = claims.get('restaurant_id')
        if assigned != restaurant_id:
            return make_response(403, {'error': 'Access denied'})

    try:
        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        item = resp.get('Item')
        if not item:
            return make_response(404, {'error': 'Restaurant not found'})

        # Customers and unauthenticated users may only see active restaurants.
        if role not in ('admin', 'restaurant_admin') and not item.get('active'):
            return make_response(404, {'error': 'Restaurant not found'})

        return make_response(200, _serialize_restaurant_for_role(item, role))
    except Exception as e:
        logger.error("get_restaurant_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
        return make_response(500, {'error': 'Internal server error'})


def list_restaurants(event):
    """List restaurants from DynamoDB, filtered by role."""
    if not restaurants_table:
        return make_response(500, {'error': 'Restaurants table not configured'})

    claims = get_user_claims(event)
    role = claims.get('role')
    assigned_restaurant_id = claims.get('restaurant_id')

    try:
        if role == 'restaurant_admin':
            if not assigned_restaurant_id:
                return make_response(403, {'error': 'No restaurant assigned to this user'})

            resp = restaurants_table.get_item(Key={'restaurant_id': assigned_restaurant_id})
            item = resp.get('Item')
            items = [item] if item else []
            next_key = None
        else:
            query_params = event.get('queryStringParameters') or {}
            cuisine_filter = query_params.get('cuisine')
            price_tier_filter = query_params.get('price_tier')

            try:
                limit = max(1, min(int(query_params.get('limit', 25)), 100))
            except (ValueError, TypeError):
                limit = 25
            next_token = query_params.get('next_token')

            if role == 'admin' and not cuisine_filter and not price_tier_filter:
                try:
                    admin_limit = max(1, min(int(query_params.get('limit', 50)), 200))
                except (ValueError, TypeError):
                    admin_limit = 50
                scan_kwargs = {'Limit': admin_limit}
                if next_token:
                    try:
                        scan_kwargs['ExclusiveStartKey'] = json.loads(
                            base64.b64decode(next_token).decode()
                        )
                    except Exception:
                        return make_response(400, {'error': 'Invalid pagination token'})
                scan_resp = restaurants_table.scan(**scan_kwargs)
                items = scan_resp.get('Items', [])
                next_key = scan_resp.get('LastEvaluatedKey')
            elif cuisine_filter:
                kwargs = {
                    'IndexName': 'GSI_Cuisine',
                    'KeyConditionExpression': Key('cuisine').eq(cuisine_filter),
                    'Limit': limit,
                }
                if next_token:
                    try:
                        kwargs['ExclusiveStartKey'] = json.loads(
                            base64.b64decode(next_token).decode()
                        )
                    except Exception:
                        return make_response(400, {'error': 'Invalid pagination token'})
                resp = restaurants_table.query(**kwargs)
                items = resp.get('Items', [])
                next_key = resp.get('LastEvaluatedKey')
            elif price_tier_filter:
                try:
                    pt = int(price_tier_filter)
                    kwargs = {
                        'IndexName': 'GSI_PriceTier',
                        'KeyConditionExpression': Key('price_tier').eq(pt),
                        'Limit': limit,
                    }
                    if next_token:
                        try:
                            kwargs['ExclusiveStartKey'] = json.loads(
                                base64.b64decode(next_token).decode()
                            )
                        except Exception:
                            return make_response(400, {'error': 'Invalid pagination token'})
                    resp = restaurants_table.query(**kwargs)
                except ValueError:
                    resp = {'Items': []}
                items = resp.get('Items', [])
                next_key = resp.get('LastEvaluatedKey')
            else:
                kwargs = {
                    'IndexName': 'GSI_ActiveRestaurants',
                    'KeyConditionExpression': Key('is_active').eq("1"),
                    'Limit': limit,
                }
                if next_token:
                    try:
                        kwargs['ExclusiveStartKey'] = json.loads(
                            base64.b64decode(next_token).decode()
                        )
                    except Exception:
                        return make_response(400, {'error': 'Invalid pagination token'})
                resp = restaurants_table.query(**kwargs)
                items = resp.get('Items', [])
                next_key = resp.get('LastEvaluatedKey')

        response_items = [_serialize_restaurant_for_role(item, role) for item in items]

        result = {'restaurants': response_items}
        if next_key:
            result['next_token'] = base64.b64encode(
                json.dumps(next_key, default=decimal_default).encode()
            ).decode()

        return make_response(200, result)
    except Exception as e:
        logger.error("list_restaurants_failed", extra={"error": str(e)})
        return make_response(500, {'error': 'Internal server error'})


def create_restaurant(event):
    """Create a new restaurant in DynamoDB."""
    if not restaurants_table or not config_table:
        return make_response(500, {'error': 'Tables not configured'})

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return make_response(403, {'error': 'Access denied: Only admins can perform this action'})

    try:
        body = json.loads(event.get('body', '{}'))
        name = body.get('name')

        if not name:
            return make_response(400, {'error': 'Restaurant name is required'})

        contact_email = body.get('contact_email')
        if contact_email and USER_POOL_ID:
            # BL-006: Validate email format to prevent Cognito filter injection.
            if not re.match(r'^[a-zA-Z0-9._+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', contact_email):
                return make_response(400, {'error': 'Invalid email format'})
            try:
                filter_str = f"email = \"{contact_email}\""
                response = cognito.list_users(
                    UserPoolId=USER_POOL_ID,
                    Filter=filter_str,
                    Limit=1
                )
                if response.get('Users'):
                    logger.info("create_restaurant_email_exists", extra={"contact_email": contact_email})
                    return make_response(409, {'error': f"User with email {contact_email} already exists. Please use a new email or delete the existing user."})
            except Exception as e:
                logger.warning("cognito_precheck_failed", extra={"contact_email": contact_email, "error": str(e)})
                pass

        restaurant_id = str(uuid.uuid4())
        timestamp = int(time.time())

        raw_image_keys = None
        if 'restaurant_image_keys' in body:
            raw_image_keys = body.get('restaurant_image_keys')
        elif 'restaurant_images' in body:
            raw_image_keys = body.get('restaurant_images')

        restaurant_image_keys = _normalize_restaurant_image_keys(
            raw_image_keys if raw_image_keys is not None else [],
            restaurant_id
        )

        street = body.get('street', '')
        city = body.get('city', '')
        state = body.get('state', '')
        zip_code = body.get('zip', '')
        full_address = f"{street}, {city}, {state} {zip_code}".strip(", ")

        location = geocode_address(street, city, state, zip_code)

        restaurant_item = {
            'restaurant_id': restaurant_id,
            'name': name,
            'address': full_address,
            'street': street,
            'city': city,
            'state': state,
            'zip': zip_code,
            'location': location,
            'vicinity_zone': {'radius': 5000},
            'contact_email': body.get('contact_email', ''),
            'active': False,
            'created_at': timestamp,
            'updated_at': timestamp,
            'cuisine': body.get('cuisine', 'Other'),
            'price_tier': max(1, min(int(body.get('price_tier', 1)), 5)),
            'tags': body.get('tags', []),
            'rating': Decimal(str(body.get('rating', '0.0'))),
            'restaurant_image_keys': restaurant_image_keys,
        }

        config_item = {
            'restaurant_id': restaurant_id,
            'active_menu_version': 'latest',
            'max_concurrent_orders': 10,
            'capacity_window_seconds': 300,
            'dispatch_trigger_zone': DEFAULT_DISPATCH_TRIGGER_ZONE,
            'dispatch_trigger_event': ZONE_EVENT_MAP[DEFAULT_DISPATCH_TRIGGER_ZONE],
            'configuration': {
                'operating_hours': body.get('operating_hours', '9:00-22:00'),
                'timezone': body.get('timezone', 'UTC')
            },
            'created_at': timestamp
        }

        restaurants_table.put_item(Item=restaurant_item)
        config_table.put_item(Item=config_item)

        # Keep AWS Location geofences in sync for automated arrival detection.
        if not upsert_restaurant_geofences(restaurant_id, location):
            logger.warning("geofence_sync_skipped", extra={"restaurant_id": restaurant_id})

        user_created = False
        contact_email = body.get('contact_email')
        if contact_email and USER_POOL_ID:
            try:
                cognito.admin_create_user(
                    UserPoolId=USER_POOL_ID,
                    Username=contact_email,
                    UserAttributes=[
                        {'Name': 'email', 'Value': contact_email},
                        {'Name': 'email_verified', 'Value': 'true'},
                        {'Name': 'custom:role', 'Value': 'restaurant_admin'},
                        {'Name': 'custom:restaurant_id', 'Value': restaurant_id}
                    ],
                    DesiredDeliveryMediums=['EMAIL']
                )
                user_created = True
                logger.info("cognito_user_created", extra={"contact_email": contact_email})
            except cognito.exceptions.UsernameExistsException:
                logger.info("cognito_user_exists", extra={"contact_email": contact_email})
                try:
                    cognito.admin_update_user_attributes(
                        UserPoolId=USER_POOL_ID,
                        Username=contact_email,
                        UserAttributes=[
                            {'Name': 'custom:role', 'Value': 'restaurant_admin'},
                            {'Name': 'custom:restaurant_id', 'Value': restaurant_id}
                        ]
                    )
                    user_created = False
                    logger.info("cognito_user_attributes_updated", extra={"contact_email": contact_email})
                except Exception as ex:
                    logger.error("cognito_user_update_failed", extra={"contact_email": contact_email, "error": str(ex)})
            except Exception as e:
                logger.error("cognito_user_create_failed", extra={"contact_email": contact_email, "error": str(e)})

        return make_response(201, {
            'restaurant_id': restaurant_id,
            'user_created': user_created,
            'user_status': 'CREATED' if user_created else 'LINKED'
        })

    except ValueError as ve:
        return make_response(400, {'error': str(ve)})
    except Exception as e:
        logger.error("create_restaurant_failed", extra={"error": str(e)})
        return make_response(500, {'error': 'Internal server error'})


def update_restaurant(event, restaurant_id):
    """Update an existing restaurant."""
    if not restaurants_table:
        return make_response(500, {'error': 'Tables not configured'})

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return make_response(403, {'error': 'Access denied'})

    try:
        body = json.loads(event.get('body', '{}'))

        # BL-002: Only platform admins may change the 'active' field.
        if not is_admin and 'active' in body:
            del body['active']

        # Only platform admins may set the rating field.
        if not is_admin and 'rating' in body:
            del body['rating']

        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        if 'Item' not in resp:
            return make_response(404, {'error': 'Restaurant not found'})

        existing_item = resp['Item']

        name = body.get('name', existing_item.get('name'))
        # contact_email is immutable — it is the Cognito identity key for the account.
        contact_email = existing_item.get('contact_email')

        street = body.get('street', existing_item.get('street', ''))
        city = body.get('city', existing_item.get('city', ''))
        state = body.get('state', existing_item.get('state', ''))
        zip_code = body.get('zip', existing_item.get('zip', ''))

        cuisine = body.get('cuisine')
        price_tier = body.get('price_tier')
        tags = body.get('tags')
        rating = body.get('rating')
        raw_image_keys = None
        if 'restaurant_image_keys' in body:
            raw_image_keys = body.get('restaurant_image_keys')
        elif 'restaurant_images' in body:
            raw_image_keys = body.get('restaurant_images')

        restaurant_image_keys = _normalize_restaurant_image_keys(raw_image_keys, restaurant_id)

        should_geocode = (
            street != existing_item.get('street') or
            city != existing_item.get('city') or
            state != existing_item.get('state') or
            zip_code != existing_item.get('zip') or
            existing_item.get('location') is None
        )

        location = existing_item.get('location')
        full_address = existing_item.get('address', '')

        if should_geocode:
            full_address = f"{street}, {city}, {state} {zip_code}".strip(", ")
            logger.info("geocoding_address", extra={"restaurant_id": restaurant_id, "address": full_address})
            new_location = geocode_address(street, city, state, zip_code)
            if new_location:
                location = new_location
            else:
                logger.warning("geocoding_failed_keeping_old", extra={"restaurant_id": restaurant_id})

        active = body.get('active')

        expr_attr_names = {
            '#n': 'name',
            '#st': 'state',
            '#l': 'location'
        }
        expr_attr_values = {
            ':n': name,
            ':e': contact_email,
            ':s': street,
            ':c': city,
            ':st': state,
            ':z': zip_code,
            ':addr': full_address,
            ':l': location,
            ':u': int(time.time())
        }

        set_parts = ["#n = :n", "contact_email = :e", "street = :s", "city = :c", "#st = :st", "zip = :z", "address = :addr", "#l = :l", "updated_at = :u"]
        remove_parts = []

        if cuisine:
            set_parts.append("cuisine = :cu")
            expr_attr_values[':cu'] = cuisine
        if price_tier is not None:
            set_parts.append("price_tier = :pt")
            expr_attr_values[':pt'] = max(1, min(int(price_tier), 5))
        if tags is not None:
            set_parts.append("tags = :tg")
            expr_attr_values[':tg'] = tags
        if rating is not None:
            set_parts.append("rating = :rt")
            expr_attr_values[':rt'] = Decimal(str(rating))
        if restaurant_image_keys is not None:
            set_parts.append("restaurant_image_keys = :rik")
            expr_attr_values[':rik'] = restaurant_image_keys

        if active is not None:
            set_parts.append("active = :a")
            expr_attr_values[':a'] = active
            if active is True:
                set_parts.append("is_active = :ia")
                expr_attr_values[':ia'] = "1"
            else:
                remove_parts.append("is_active")

        update_expr = "SET " + ", ".join(set_parts)
        if remove_parts:
            update_expr += " REMOVE " + ", ".join(remove_parts)

        restaurants_table.update_item(
            Key={'restaurant_id': restaurant_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

        if not upsert_restaurant_geofences(restaurant_id, location):
            logger.warning("geofence_update_skipped", extra={"restaurant_id": restaurant_id})

        return make_response(200, {
            'message': 'Restaurant updated',
            'location': location
        })

    except ValueError as ve:
        return make_response(400, {'error': str(ve)})
    except Exception as e:
        logger.error("update_restaurant_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
        return make_response(500, {'error': 'Internal server error'})


def delete_restaurant(event, restaurant_id):
    """Delete a restaurant and its associated data."""
    if not restaurants_table:
        return make_response(500, {'error': 'Tables not configured'})

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return make_response(403, {'error': 'Access denied'})

    try:
        if USER_POOL_ID:
            try:
                contact_email = None
                resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
                if 'Item' in resp:
                    contact_email = resp['Item'].get('contact_email')

                if contact_email:
                    logger.info("cognito_user_delete_attempt", extra={"contact_email": contact_email})
                    filter_str = f"email = \"{contact_email}\""
                    response = cognito.list_users(
                        UserPoolId=USER_POOL_ID,
                        Filter=filter_str,
                        Limit=1
                    )

                    for user in response.get('Users', []):
                        username = user['Username']
                        logger.info("cognito_user_deleting", extra={"username": username})
                        cognito.admin_delete_user(
                            UserPoolId=USER_POOL_ID,
                            Username=username
                        )
                else:
                    logger.info("cognito_cleanup_skipped_no_email", extra={"restaurant_id": restaurant_id})

            except Exception as e:
                logger.warning("cognito_cleanup_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})

        restaurants_table.delete_item(Key={'restaurant_id': restaurant_id})
        if not delete_restaurant_geofences(restaurant_id):
            logger.warning("geofence_delete_skipped", extra={"restaurant_id": restaurant_id})
        if config_table:
            config_table.delete_item(Key={'restaurant_id': restaurant_id})
        if menus_table:
            try:
                menu_resp = menus_table.query(
                    KeyConditionExpression=Key('restaurant_id').eq(restaurant_id)
                )
                for menu_item in menu_resp.get('Items', []):
                    menus_table.delete_item(Key={
                        'restaurant_id': restaurant_id,
                        'menu_version': menu_item['menu_version']
                    })
            except Exception as menu_err:
                logger.warning("menu_cleanup_failed", extra={"restaurant_id": restaurant_id, "error": str(menu_err)})

        return make_response(200, {'message': 'Restaurant deleted'})

    except Exception as e:
        logger.error("delete_restaurant_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
        return make_response(500, {'error': 'Internal server error'})
