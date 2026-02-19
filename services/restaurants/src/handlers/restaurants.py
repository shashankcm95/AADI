"""Restaurant CRUD handlers."""
import json
import base64
import uuid
import time
import traceback
from decimal import Decimal
from boto3.dynamodb.conditions import Attr, Key

from utils import (
    CORS_HEADERS, decimal_default, get_user_claims,
    restaurants_table, config_table, cognito, USER_POOL_ID,
    geocode_address, _normalize_restaurant_image_keys, _decorate_restaurant_response,
    menus_table,
)


def list_restaurants(event):
    """List restaurants from DynamoDB, filtered by role."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurants table not configured'})}

    claims = get_user_claims(event)
    role = claims.get('role')
    assigned_restaurant_id = claims.get('restaurant_id')

    try:
        if role == 'restaurant_admin':
            if not assigned_restaurant_id:
                return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'No restaurant assigned to this user'})}

            resp = restaurants_table.get_item(Key={'restaurant_id': assigned_restaurant_id})
            item = resp.get('Item')
            items = [item] if item else []
            next_key = None
        else:
            query_params = event.get('queryStringParameters') or {}
            cuisine_filter = query_params.get('cuisine')
            price_tier_filter = query_params.get('price_tier')

            try:
                limit = min(int(query_params.get('limit', 25)), 100)
            except (ValueError, TypeError):
                limit = 25
            next_token = query_params.get('next_token')

            if role == 'admin' and not cuisine_filter and not price_tier_filter:
                scan_resp = restaurants_table.scan()
                items = scan_resp.get('Items', [])
                while 'LastEvaluatedKey' in scan_resp:
                    scan_resp = restaurants_table.scan(
                        ExclusiveStartKey=scan_resp['LastEvaluatedKey']
                    )
                    items.extend(scan_resp.get('Items', []))
                next_key = None
            elif cuisine_filter:
                kwargs = {
                    'IndexName': 'GSI_Cuisine',
                    'KeyConditionExpression': Key('cuisine').eq(cuisine_filter),
                    'Limit': limit,
                }
                if next_token:
                    kwargs['ExclusiveStartKey'] = json.loads(
                        base64.b64decode(next_token).decode()
                    )
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
                        kwargs['ExclusiveStartKey'] = json.loads(
                            base64.b64decode(next_token).decode()
                        )
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
                    kwargs['ExclusiveStartKey'] = json.loads(
                        base64.b64decode(next_token).decode()
                    )
                resp = restaurants_table.query(**kwargs)
                items = resp.get('Items', [])
                next_key = resp.get('LastEvaluatedKey')

                if not items and not next_token:
                    scan_resp = restaurants_table.scan(
                        FilterExpression=Attr('active').eq(True)
                    )
                    items = scan_resp.get('Items', [])
                    while 'LastEvaluatedKey' in scan_resp:
                        scan_resp = restaurants_table.scan(
                            FilterExpression=Attr('active').eq(True),
                            ExclusiveStartKey=scan_resp['LastEvaluatedKey']
                        )
                        items.extend(scan_resp.get('Items', []))
                    next_key = None

        response_items = [_decorate_restaurant_response(item) for item in items]

        result = {'restaurants': response_items}
        if next_key:
            result['next_token'] = base64.b64encode(
                json.dumps(next_key, default=decimal_default).encode()
            ).decode()

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(result, default=decimal_default)
        }
    except Exception as e:
        print(f"Scan Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def create_restaurant(event):
    """Create a new restaurant in DynamoDB."""
    if not restaurants_table or not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied: Only admins can perform this action'})}

    try:
        body = json.loads(event.get('body', '{}'))
        name = body.get('name')

        if not name:
            return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant name is required'})}

        contact_email = body.get('contact_email')
        if contact_email and USER_POOL_ID:
            try:
                filter_str = f"email = \"{contact_email}\""
                response = cognito.list_users(
                    UserPoolId=USER_POOL_ID,
                    Filter=filter_str,
                    Limit=1
                )
                if response.get('Users'):
                    print(f"User {contact_email} already exists. Blocking creation.")
                    return {
                        'statusCode': 409,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'error': f"User with email {contact_email} already exists. Please use a new email or delete the existing user."})
                    }
            except Exception as e:
                print(f"Pre-check user existence failed: {e}")
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
            'price_tier': int(body.get('price_tier', 1)),
            'tags': body.get('tags', []),
            'rating': Decimal(str(body.get('rating', '0.0'))),
            'restaurant_image_keys': restaurant_image_keys,
        }

        config_item = {
            'restaurant_id': restaurant_id,
            'active_menu_version': 'latest',
            'max_concurrent_orders': 10,
            'capacity_window_seconds': 300,
            'configuration': {
                'operating_hours': body.get('operating_hours', '9:00-22:00'),
                'timezone': body.get('timezone', 'UTC')
            },
            'created_at': timestamp
        }

        restaurants_table.put_item(Item=restaurant_item)
        config_table.put_item(Item=config_item)

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
                print(f"Created Cognito user for {contact_email}")
            except cognito.exceptions.UsernameExistsException:
                print(f"User {contact_email} already exists")
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
                    print(f"Updated attributes for existing user {contact_email}")
                except Exception as ex:
                    print(f"Failed to update existing user: {ex}")
            except Exception as e:
                print(f"Failed to create Cognito user: {e}")

        return {
            'statusCode': 201,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'user_created': user_created,
                'user_status': 'CREATED' if user_created else 'LINKED'
            }, default=decimal_default)
        }

    except ValueError as ve:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(ve)})}
    except Exception as e:
        print(f"Create Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def update_restaurant(event, restaurant_id):
    """Update an existing restaurant."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        body = json.loads(event.get('body', '{}'))

        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        if 'Item' not in resp:
            return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant not found'})}

        existing_item = resp['Item']

        name = body.get('name', existing_item.get('name'))
        contact_email = body.get('contact_email', existing_item.get('contact_email'))

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
            print(f"Address changed or location missing, re-geocoding: {full_address}")
            new_location = geocode_address(street, city, state, zip_code)
            if new_location:
                location = new_location
            else:
                print("Geocoding failed, keeping old location (if any) or None")
                pass

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
            expr_attr_values[':pt'] = int(price_tier)
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

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'message': 'Restaurant updated',
                'location': location
            }, default=decimal_default)
        }

    except ValueError as ve:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(ve)})}
    except Exception as e:
        print(f"Update Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def delete_restaurant(event, restaurant_id):
    """Delete a restaurant and its associated data."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        if USER_POOL_ID:
            try:
                contact_email = None
                resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
                if 'Item' in resp:
                    contact_email = resp['Item'].get('contact_email')

                if contact_email:
                    print(f"Attempting to delete Cognito user with email: {contact_email}")
                    filter_str = f"email = \"{contact_email}\""
                    response = cognito.list_users(
                        UserPoolId=USER_POOL_ID,
                        Filter=filter_str,
                        Limit=1
                    )

                    for user in response.get('Users', []):
                        username = user['Username']
                        print(f"Deleting Cognito user: {username}")
                        cognito.admin_delete_user(
                            UserPoolId=USER_POOL_ID,
                            Username=username
                        )
                else:
                    print("No contact email found for restaurant, skipping Cognito cleanup")

            except Exception as e:
                print(f"Cognito cleanup failed (non-blocking): {e}")

        restaurants_table.delete_item(Key={'restaurant_id': restaurant_id})
        if config_table:
            config_table.delete_item(Key={'restaurant_id': restaurant_id})
        if menus_table:
            pass

        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({'message': 'Restaurant deleted'})}

    except Exception as e:
        print(f"Delete Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}
