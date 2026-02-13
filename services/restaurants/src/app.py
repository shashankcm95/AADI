import json
import os
import boto3
import traceback
import uuid
import time
import urllib.request
import urllib.parse
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB resources
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')

RESTAURANTS_TABLE = os.environ.get('RESTAURANTS_TABLE')
MENUS_TABLE = os.environ.get('MENUS_TABLE')
RESTAURANT_CONFIG_TABLE = os.environ.get('RESTAURANT_CONFIG_TABLE')
USER_POOL_ID = os.environ.get('USER_POOL_ID')

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



import re

def _call_nominatim(query):
    """Helper to call Nominatim API."""
    try:
        params = urllib.parse.urlencode({'q': query, 'format': 'json', 'limit': 1})
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        
        headers = {'User-Agent': 'AADI-Restaurant-Service/1.0 (admin@aadieats.com)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data:
                print(f"Geocoding success for '{query}': {data[0]['lat']}, {data[0]['lon']}")
                return {
                    'lat': Decimal(str(data[0]['lat'])),
                    'lon': Decimal(str(data[0]['lon']))
                }
    except Exception as e:
        print(f"Geocoding error for '{query}': {e}")
    return None


def geocode_address(street, city, state, zip_code):
    """Geocode address with retry logic for unit numbers."""
    # 1. Try exact address
    full_address = f"{street}, {city}, {state} {zip_code}"
    result = _call_nominatim(full_address)
    if result:
        return result
    
    # 2. Try stripping unit numbers (e.g. #250, Apt 1, Suite 100)
    # Regex looks for " #..." or " Apt..." at end of string
    cleaned_street = re.sub(r'(?i)[\s,]+(?:#|apt|suite|ste|unit)[\s.]*[\w-]+.*$', '', street)
    
    if cleaned_street != street:
        print(f"Retrying geocoding without unit: {cleaned_street}")
        full_address_clean = f"{cleaned_street}, {city}, {state} {zip_code}"
        result = _call_nominatim(full_address_clean)
        if result:
            return result
            
    # 3. Last resort: Just Street (cleaned), City, State, Zip (might be too broad but better than nothing?)
    # or fail. Let's return None to be safe.
    print(f"Geocoding failed for all attempts: {full_address}")
    return None
    return None


def get_user_claims(event):
    """Extract user claims from the event."""
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        return {
            'role': claims.get('custom:role'),
            'restaurant_id': claims.get('custom:restaurant_id')
        }
    except (KeyError, TypeError):
        return {}


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
            return list_restaurants(event)

        if route_key == 'POST /v1/restaurants':
            return create_restaurant(event)

        if route_key == 'PUT /v1/restaurants/{restaurant_id}':
            return update_restaurant(event, path_params.get('restaurant_id'))

        if route_key == 'DELETE /v1/restaurants/{restaurant_id}':
            return delete_restaurant(event, path_params.get('restaurant_id'))

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


def list_restaurants(event):
    """List restaurants from DynamoDB, filtered by role."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurants table not configured'})}

    claims = get_user_claims(event)
    role = claims.get('role')
    assigned_restaurant_id = claims.get('restaurant_id')

    try:
        # If restaurant_admin, only return their assigned restaurant
        if role == 'restaurant_admin':
            if not assigned_restaurant_id:
                return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'No restaurant assigned to this user'})}
            
            resp = restaurants_table.get_item(Key={'restaurant_id': assigned_restaurant_id})
            item = resp.get('Item')
            items = [item] if item else []
        else:
            # Admin (or others) sees all active restaurants
            resp = restaurants_table.scan()
            items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'restaurants': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Scan Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def update_restaurant(event, restaurant_id):
    """Update an existing restaurant."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    # RBAC Check
    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')
    
    # Allow if Admin OR if Restaurant Admin updating their own restaurant
    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id
    
    if not (is_admin or is_owner):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        body = json.loads(event.get('body', '{}'))
        
        # Get existing item
        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        if 'Item' not in resp:
            return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant not found'})}
        
        existing_item = resp['Item']
        
        # Update fields
        name = body.get('name', existing_item.get('name'))
        contact_email = body.get('contact_email', existing_item.get('contact_email'))
        
        # Address Updates
        street = body.get('street', existing_item.get('street', ''))
        city = body.get('city', existing_item.get('city', ''))
        state = body.get('state', existing_item.get('state', ''))
        zip_code = body.get('zip', existing_item.get('zip', ''))
        
        # Check if address changed OR if location is missing (retry)
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
                # If geocoding failed, we might want to keep the old location if it existed,
                # but if the address changed, the old location is wrong. 
                # For now, let's only update 'location' if we got a result, 
                # OR if we explicitly want to clear it? 
                # Safest: if new address implies new location, and it failed, we arguably have NO location.
                # But to avoid data loss on transient errors, let's keep old location if new one fails,
                # unless address changed significantly? 
                # Simple approach: If geocoding returns None, we warn but don't overwrite with None unless we want to clear it.
                # But here, we assigned `location = existing...` above. 
                # If `new_location` is found, we update `location`.
                # If `new_location` is None, `location` remains old (which might be None or old coord).
                pass
        
        # Update DynamoDB
        update_expr = "SET #n = :n, contact_email = :e, street = :s, city = :c, #st = :st, zip = :z, address = :addr, #l = :l, updated_at = :u"
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
        
        restaurants_table.update_item(
            Key={'restaurant_id': restaurant_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        
        # Note: We are NOT updating the Cognito username/email here to avoid complexity with immutable usernames.
        # If needed, we could search for the user by custom:restaurant_id and update their email attribute.
        
        return {
            'statusCode': 200, 
            'headers': CORS_HEADERS, 
            'body': json.dumps({
                'message': 'Restaurant updated',
                'location': location
            }, default=decimal_default)
        }
        
    except Exception as e:
        print(f"Update Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def delete_restaurant(event, restaurant_id):
    """Delete a restaurant and its associated data."""
    if not restaurants_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    # RBAC Check
    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        # 1. Delete associated Cognito User
        if USER_POOL_ID:
            try:
                # First, get the restaurant to find the contact email
                # We need the email because searching by custom attribute is not supported
                contact_email = None
                resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
                if 'Item' in resp:
                    contact_email = resp['Item'].get('contact_email')

                if contact_email:
                    print(f"Attempting to delete Cognito user with email: {contact_email}")
                    # Filter by email (Standard Attribute)
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

        # 2. Delete from DynamoDB
        restaurants_table.delete_item(Key={'restaurant_id': restaurant_id})
        if config_table:
            config_table.delete_item(Key={'restaurant_id': restaurant_id})
        if menus_table:
            # Note: Menus table has a range key (menu_version). 
            # Ideally we query all versions and delete them, or just leave them as orphaned (low cost).
            # For strict cleanup, we'd query and delete batch. Skipping for simplicity in this iteration.
            pass

        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({'message': 'Restaurant deleted'})}

    except Exception as e:
        print(f"Delete Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def create_restaurant(event):
    """Create a new restaurant in DynamoDB."""
    if not restaurants_table or not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Tables not configured'})}

    # RBAC Check: Only admins can create restaurants
    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied: Only admins can perform this action'})}

    try:
        body = json.loads(event.get('body', '{}'))
        name = body.get('name')
        
        if not name:
            return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant name is required'})}

        # Check if user already exists (Prevent Duplicates)
        contact_email = body.get('contact_email')
        if contact_email and USER_POOL_ID:
            try:
                # We use list_users because admin_get_user throws if not found, 
                # and list_users is cleaner for "check existence"
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
                # We continue? Or fail? Best to fail safe if we can't check.
                # But let's log and continue to allow creation if check flakes.
                pass

        # Check if user already exists (Prevent Duplicates)
        contact_email = body.get('contact_email')
        if contact_email and USER_POOL_ID:
            try:
                # We use list_users because admin_get_user throws if not found, 
                # and list_users is cleaner for "check existence"
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
                # We continue? Or fail? Best to fail safe if we can't check.
                # But let's log and continue to allow creation if check flakes.
                pass

        # Generate a unique ID
        restaurant_id = str(uuid.uuid4())
        timestamp = int(time.time())

        # Address & Geocoding
        street = body.get('street', '')
        city = body.get('city', '')
        state = body.get('state', '')
        zip_code = body.get('zip', '')
        full_address = f"{street}, {city}, {state} {zip_code}".strip(", ")
        
        location = geocode_address(street, city, state, zip_code)

        # Create Restaurant Item
        restaurant_item = {
            'restaurant_id': restaurant_id,
            'name': name,
            'address': full_address,
            'street': street,
            'city': city,
            'state': state,
            'zip': zip_code,
            'location': location,  # {lat, lon} or None
            'vicinity_zone': {'radius': 5000}, # Default 5km radius
            'contact_email': body.get('contact_email', ''),
            'active': False, # Default to inactive until first login/password change
            'created_at': timestamp,
            'updated_at': timestamp
        }

        # Create Default Config Item
        config_item = {
            'restaurant_id': restaurant_id,
            'active_menu_version': 'v1',
            'configuration': {
                'operating_hours': body.get('operating_hours', '9:00-22:00'),
                'timezone': body.get('timezone', 'UTC')
            },
            'created_at': timestamp
        }

        # Write to DynamoDB
        restaurants_table.put_item(Item=restaurant_item)
        config_table.put_item(Item=config_item)

        # Create Cognito User
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
                # Try to update attributes for existing user
                try:
                    cognito.admin_update_user_attributes(
                        UserPoolId=USER_POOL_ID,
                        Username=contact_email,
                        UserAttributes=[
                            {'Name': 'custom:role', 'Value': 'restaurant_admin'},
                            {'Name': 'custom:restaurant_id', 'Value': restaurant_id}
                        ]
                    )
                    user_created = False # User already existed
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

    except Exception as e:
        print(f"Create Error: {e}")
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
