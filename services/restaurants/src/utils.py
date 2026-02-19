"""Shared utilities for the restaurants service."""
import json
import os
import re
import urllib.request
import urllib.parse
from decimal import Decimal

import boto3


# ---------------------------------------------------------------------------
# DynamoDB & AWS resources (initialised once at import / cold-start)
# ---------------------------------------------------------------------------
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')

RESTAURANTS_TABLE = os.environ.get('RESTAURANTS_TABLE')
MENUS_TABLE = os.environ.get('MENUS_TABLE')
RESTAURANT_CONFIG_TABLE = os.environ.get('RESTAURANT_CONFIG_TABLE')
FAVORITES_TABLE = os.environ.get('FAVORITES_TABLE')
RESTAURANT_IMAGES_BUCKET = os.environ.get('RESTAURANT_IMAGES_BUCKET')
USER_POOL_ID = os.environ.get('USER_POOL_ID')

try:
    IMAGE_URL_TTL_SECONDS = int(os.environ.get('IMAGE_URL_TTL_SECONDS', '3600'))
except (TypeError, ValueError):
    IMAGE_URL_TTL_SECONDS = 3600

restaurants_table = dynamodb.Table(RESTAURANTS_TABLE) if RESTAURANTS_TABLE else None
menus_table = dynamodb.Table(MENUS_TABLE) if MENUS_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None
favorites_table = dynamodb.Table(FAVORITES_TABLE) if FAVORITES_TABLE else None
s3_client = boto3.client('s3')


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def get_user_claims(event):
    """Extract user claims from the event."""
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        role = claims.get('custom:role') or claims.get('role')
        restaurant_id = claims.get('custom:restaurant_id') or claims.get('restaurant_id')
        customer_id = claims.get('sub')

        # Legacy/federated users may not carry custom role attributes.
        if not role and customer_id and not restaurant_id:
            role = 'customer'

        return {
            'role': role,
            'restaurant_id': restaurant_id,
            'customer_id': customer_id,
            'username': claims.get('cognito:username') or claims.get('username')
        }
    except (KeyError, TypeError):
        return {}


def _is_admin_or_owner(claims, restaurant_id):
    role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')
    return role == 'admin' or (role == 'restaurant_admin' and user_restaurant_id == restaurant_id)


def _require_customer(event):
    claims = get_user_claims(event)
    customer_id = claims.get('customer_id')
    role = claims.get('role')
    restaurant_id = claims.get('restaurant_id')

    if not customer_id:
        return None, {'statusCode': 401, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Unauthorized'})}

    # Accept role-less users as customers only when not bound to a restaurant.
    is_customer = role == 'customer' or (not role and not restaurant_id)
    if not is_customer:
        return None, {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    return customer_id, None


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------
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
    full_address = f"{street}, {city}, {state} {zip_code}"
    result = _call_nominatim(full_address)
    if result:
        return result

    cleaned_street = re.sub(r'(?i)[\s,]+(?:#|apt|suite|ste|unit)[\s.]*[\w-]+.*$', '', street)

    if cleaned_street != street:
        print(f"Retrying geocoding without unit: {cleaned_street}")
        full_address_clean = f"{cleaned_street}, {city}, {state} {zip_code}"
        result = _call_nominatim(full_address_clean)
        if result:
            return result

    print(f"Geocoding failed for all attempts: {full_address}")
    return None


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def _extract_s3_object_key(value):
    candidate = str(value or '').strip()
    if not candidate:
        return ''

    if candidate.startswith('s3://'):
        no_scheme = candidate[len('s3://'):]
        parts = no_scheme.split('/', 1)
        return parts[1] if len(parts) == 2 else ''

    if 'amazonaws.com/' in candidate:
        return candidate.split('amazonaws.com/', 1)[1].split('?', 1)[0].lstrip('/')

    return candidate.lstrip('/')


def _normalize_restaurant_image_keys(raw_keys, restaurant_id):
    if raw_keys is None:
        return None

    if not isinstance(raw_keys, list):
        raise ValueError('restaurant_image_keys must be a list')

    prefix = f"restaurants/{restaurant_id}/"
    normalized = []

    for entry in raw_keys:
        key = _extract_s3_object_key(entry)
        if not key:
            continue
        if not key.startswith(prefix):
            raise ValueError('All restaurant_image_keys must belong to this restaurant')
        if key not in normalized:
            normalized.append(key)

    if len(normalized) > 5:
        raise ValueError('A maximum of 5 restaurant images is allowed')

    return normalized


def _build_image_url(object_key, expires_in=IMAGE_URL_TTL_SECONDS):
    if not object_key or not RESTAURANT_IMAGES_BUCKET:
        return None

    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': RESTAURANT_IMAGES_BUCKET,
                'Key': object_key,
            },
            ExpiresIn=max(60, int(expires_in)),
        )
    except Exception as e:
        print(f"Failed to generate image URL for {object_key}: {e}")
        return None


def _decorate_restaurant_response(item):
    if not isinstance(item, dict):
        return item

    response_item = dict(item)
    raw_keys = response_item.get('restaurant_image_keys')
    image_keys = raw_keys if isinstance(raw_keys, list) else []

    image_urls = []
    for key in image_keys[:5]:
        url = _build_image_url(_extract_s3_object_key(key))
        if url:
            image_urls.append(url)

    response_item['restaurant_images'] = image_urls
    if image_urls:
        if not response_item.get('image_url'):
            response_item['image_url'] = image_urls[0]
        if len(image_urls) > 1 and not response_item.get('banner_image_url'):
            response_item['banner_image_url'] = image_urls[1]

    return response_item
