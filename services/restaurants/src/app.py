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

    # Global Access Check for Restaurant Admins
    claims = get_user_claims(event)
    role = claims.get('role')
    restaurant_id = claims.get('restaurant_id')

    # If user is a restaurant admin, ensure their restaurant is active
    if role == 'restaurant_admin' and restaurant_id:
        try:
            resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
            restaurant = resp.get('Item')
            
            # If restaurant not found or not active, deny access
            # EXCEPTION: Allow GET /v1/restaurants (so they can see their status)
            if restaurant and not restaurant.get('active', False):
                # Allow read-only access to their own restaurant details to see "Inactive" status
                allowed_routes = ['GET /v1/restaurants']
                if route_key not in allowed_routes:
                    print(f"Blocking access for inactive restaurant {restaurant_id}")
                    return {
                        'statusCode': 403,
                        'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'Restaurant is currently inactive/on-hold. Please contact support.'})
                    }
        except Exception as e:
            print(f"Error checking restaurant status: {e}")
            # Fail closed if DB error? Or allow and let downstream handle?
            # Safer to fail closed for security/compliance.
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Internal authorization error'})}

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
            # Check for filters
            query_params = event.get('queryStringParameters') or {}
            cuisine_filter = query_params.get('cuisine')
            price_tier_filter = query_params.get('price_tier')

            if cuisine_filter:
                resp = restaurants_table.query(
                    IndexName='GSI_Cuisine',
                    KeyConditionExpression=Key('cuisine').eq(cuisine_filter)
                )
            elif price_tier_filter:
                try:
                    pt = int(price_tier_filter)
                    resp = restaurants_table.query(
                        IndexName='GSI_PriceTier',
                        KeyConditionExpression=Key('price_tier').eq(pt)
                    )
                except ValueError:
                    # Fallback or empty if invalid
                    resp = {'Items': []}
            else:
                resp = restaurants_table.query(
                    IndexName='GSI_ActiveRestaurants',
                    KeyConditionExpression=Key('is_active').eq("1")
                )
            items = resp.get('Items', [])

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'restaurants': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Scan Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def update_menu(event, restaurant_id):
    """Update (Overwrite) the menu for a restaurant."""
    if not menus_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Menus table not configured'})}

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
        items = body.get('items', [])
        
        print(f"Received {len(items)} items for restaurant {restaurant_id}")
        if len(items) > 0:
            print(f"Sample Item: {items[0]}")
        
        if not isinstance(items, list):
            return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Payload must contain an "items" list'})}

        # Basic validation
        cleaned_items = []
        for item in items:
            # Check for keys case-insensitively just in case, but frontend sends lowercase
            # We expect 'name' and 'price'
            
            if not item.get('name') or item.get('price') is None:
                print(f"Skipping item due to missing fields: {item}")
                continue # Skip invalid items
            
            # Ensure price is number/string decimal
            try:
                # Handle price as string, strip '$', ',' and whitespace
                price_str = str(item['price']).replace('$', '').replace(',', '').strip()
                # Convert float to Decimal for DynamoDB
                price = Decimal(price_str)
                item['price'] = price
                
                # ALSO store price_cents (integer) for frontend/order service compatibility
                # price is Decimal('5.99') -> float(5.99) -> 5.99 * 100 -> 599
                item['price_cents'] = int(float(price) * 100)
            except Exception as e:
                print(f"Skipping key {item.get('name')} due to invalid price: {item.get('price')} - Error: {e}")
                continue
                
            # Ensure ID exists
            if not item.get('id'):
                item['id'] = str(uuid.uuid4())

            cleaned_items.append(item)
            
        print(f"Cleaned items count: {len(cleaned_items)}")

        # Store in DynamoDB
        # We use a fixed version 'latest' for the active menu
        menu_item = {
            'restaurant_id': restaurant_id,
            'menu_version': 'latest',
            'items': cleaned_items,
            'updated_at': int(time.time()),
            'updated_by': claims.get('username', 'unknown')
        }
        
        menus_table.put_item(Item=menu_item)
        
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'message': 'Menu updated successfully', 'count': len(cleaned_items)})
        }
            
    except Exception as e:
        print(f"Menu Update Error: {e}")
        traceback.print_exc()
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

        # Metadata Updates
        cuisine = body.get('cuisine')
        price_tier = body.get('price_tier')
        tags = body.get('tags')
        rating = body.get('rating')
        
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
        
        active = body.get('active')
        
        # Prepare Update Expression
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

        # Construct expression to handle REMOVE safely
        set_parts = ["#n = :n", "contact_email = :e", "street = :s", "city = :c", "#st = :st", "zip = :z", "address = :addr", "#l = :l", "updated_at = :u"]
        remove_parts = []
        
        # New Metadata SET parts
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
            'updated_at': timestamp,
            # Metadata Enhancements
            'cuisine': body.get('cuisine', 'Other'),
            'price_tier': int(body.get('price_tier', 1)), # 1-4
            'tags': body.get('tags', []), # List of strings
            'rating': Decimal(str(body.get('rating', '0.0')))
        }

        # Create Default Config Item
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
        # Now get the menu for that version
        # For now, we only support 'latest' which is what update_menu writes
        version = 'latest'
        
        resp = menus_table.get_item(
            Key={'restaurant_id': restaurant_id, 'menu_version': version}
        )
        item = resp.get('Item', {})
        # update_menu stores 'items' at the top level
        items = item.get('items', [])

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'items': items}, default=decimal_default)
        }
    except Exception as e:
        print(f"Menu Error: {e}")
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps({'menu': {'items': []}})}


def get_config(event, restaurant_id):
    """Get capacity configuration for a restaurant."""
    if not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Config table not configured'})}

    # RBAC Check (Allow Read if Admin or Owner)
    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')
    
    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id
    
    if not (is_admin or is_owner):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        resp = config_table.get_item(Key={'restaurant_id': restaurant_id})
        item = resp.get('Item', {})
        config = item.get('configuration', {})
        
        # Merge with defaults/legacy if needed, but 'configuration' map is where we store it.
        # Wait, the capacity.py reads top-level attributes from the item, NOT from a 'configuration' map?
        # Let's check capacity.py again. 
        # capacity.py: item.get("max_concurrent_orders", DEFAULT...)
        # So we should store them at top level of the item, OR update capacity.py. 
        # Updating app.py to validly read/write them at top level is safer for capacity.py compatibility.
        # But 'create_restaurant' created a 'configuration' map?
        # create_restaurant: 'configuration': {'operating_hours': ...}
        # It seems we have mixed schema. capacity.py expects top-level. 
        # We should expose them effectively.
        
        response_data = {
            'max_concurrent_orders': int(item.get('max_concurrent_orders', 10)),
            'capacity_window_seconds': int(item.get('capacity_window_seconds', 300)),
            'operating_hours': config.get('operating_hours'),
            'timezone': config.get('timezone')
        }

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(response_data, default=decimal_default)
        }
    except Exception as e:
        print(f"Get Config Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}


def update_config(event, restaurant_id):
    """Update capacity configuration."""
    if not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Config table not configured'})}

    # RBAC Check
    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')
    
    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id
    
    if not (is_admin or is_owner):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        body = json.loads(event.get('body', '{}'))
        
        # We support updating specific fields
        max_concurrent = body.get('max_concurrent_orders')
        window_seconds = body.get('capacity_window_seconds')
        
        update_expr_parts = []
        expr_values = {}
        
        if max_concurrent is not None:
            update_expr_parts.append("max_concurrent_orders = :m")
            expr_values[':m'] = int(max_concurrent)
            
        if window_seconds is not None:
            update_expr_parts.append("capacity_window_seconds = :w")
            expr_values[':w'] = int(window_seconds)
            
        if not update_expr_parts:
             return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'No valid fields to update'})}
             
        # We also need to update updated_at
        update_expr_parts.append("updated_at = :u")
        expr_values[':u'] = int(time.time())

        config_table.update_item(
            Key={'restaurant_id': restaurant_id},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeValues=expr_values
        )
        
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'message': 'Configuration updated'})
        }

    except Exception as e:
        print(f"Update Config Error: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}
