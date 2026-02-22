"""Shared utilities for the restaurants service."""
import json
import os
import re
import math
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
LOCATION_GEOFENCE_COLLECTION_NAME = os.environ.get('LOCATION_GEOFENCE_COLLECTION_NAME', '').strip()

try:
    IMAGE_URL_TTL_SECONDS = int(os.environ.get('IMAGE_URL_TTL_SECONDS', '3600'))
except (TypeError, ValueError):
    IMAGE_URL_TTL_SECONDS = 3600

restaurants_table = dynamodb.Table(RESTAURANTS_TABLE) if RESTAURANTS_TABLE else None
menus_table = dynamodb.Table(MENUS_TABLE) if MENUS_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None
favorites_table = dynamodb.Table(FAVORITES_TABLE) if FAVORITES_TABLE else None
s3_client = boto3.client('s3')
_location_client = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
}

GLOBAL_CONFIG_ID = '__GLOBAL__'
DEFAULT_DISPATCH_TRIGGER_ZONE = 'ZONE_1'
ZONE_EVENT_MAP = {
    'ZONE_1': '5_MIN_OUT',
    'ZONE_2': 'PARKING',
    'ZONE_3': 'AT_DOOR',
}
EVENT_ZONE_MAP = {event: zone for zone, event in ZONE_EVENT_MAP.items()}
DEFAULT_ZONE_DISTANCES_M = {
    'ZONE_1': 1500,
    'ZONE_2': 150,
    'ZONE_3': 30,
}
DEFAULT_ZONE_LABELS = {
    'ZONE_1': 'Zone 1',
    'ZONE_2': 'Zone 2',
    'ZONE_3': 'Zone 3',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def _coerce_positive_int(value, minimum=1, maximum=50_000):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return number


def normalize_dispatch_trigger_zone(raw):
    candidate = str(raw or DEFAULT_DISPATCH_TRIGGER_ZONE).strip().upper().replace('-', '_')
    if candidate == 'FIVE_MIN_OUT':
        candidate = '5_MIN_OUT'

    if candidate in EVENT_ZONE_MAP:
        return EVENT_ZONE_MAP[candidate]
    if candidate in ZONE_EVENT_MAP:
        return candidate
    return None


def normalize_dispatch_trigger_event(raw):
    zone = normalize_dispatch_trigger_zone(raw)
    if not zone:
        return None
    return ZONE_EVENT_MAP.get(zone)


def _normalize_zone_distances(raw):
    normalized = dict(DEFAULT_ZONE_DISTANCES_M)
    if not isinstance(raw, dict):
        return normalized

    for zone_name in DEFAULT_ZONE_DISTANCES_M:
        candidate = raw.get(zone_name)
        if candidate is None:
            candidate = raw.get(ZONE_EVENT_MAP[zone_name])
        parsed = _coerce_positive_int(candidate)
        if parsed is not None:
            normalized[zone_name] = parsed
    return normalized


def _normalize_zone_labels(raw):
    normalized = dict(DEFAULT_ZONE_LABELS)
    if not isinstance(raw, dict):
        return normalized

    for zone_name in DEFAULT_ZONE_LABELS:
        candidate = raw.get(zone_name)
        if candidate is None:
            continue
        label = str(candidate).strip()
        if not label:
            continue
        normalized[zone_name] = label[:48]
    return normalized


def get_global_zone_distances():
    if not config_table:
        return dict(DEFAULT_ZONE_DISTANCES_M)

    try:
        resp = config_table.get_item(Key={'restaurant_id': GLOBAL_CONFIG_ID})
        item = resp.get('Item', {})
        return _normalize_zone_distances(item.get('zone_distances_m'))
    except Exception as e:
        print(f"Failed to read global zone distances: {e}")
        return dict(DEFAULT_ZONE_DISTANCES_M)


def get_global_zone_labels():
    if not config_table:
        return dict(DEFAULT_ZONE_LABELS)

    try:
        resp = config_table.get_item(Key={'restaurant_id': GLOBAL_CONFIG_ID})
        item = resp.get('Item', {})
        return _normalize_zone_labels(item.get('zone_labels'))
    except Exception as e:
        print(f"Failed to read global zone labels: {e}")
        return dict(DEFAULT_ZONE_LABELS)


def get_geofence_radii_meters():
    zone_distances = get_global_zone_distances()
    radii = {}
    for zone_name, event_name in ZONE_EVENT_MAP.items():
        default_radius = DEFAULT_ZONE_DISTANCES_M[zone_name]
        radii[event_name] = int(zone_distances.get(zone_name, default_radius))
    return radii


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


def _get_location_client():
    global _location_client
    if _location_client is not None:
        return _location_client
    try:
        _location_client = boto3.client('location')
    except Exception as e:
        print(f"Amazon Location client unavailable: {e}")
        _location_client = False
    return _location_client if _location_client else None


def _build_circle_polygon(latitude, longitude, radius_meters, segments=12):
    # Build a simple geodesic circle approximation as required by Location polygons.
    earth_radius_m = 6_371_000.0
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    angular_distance = float(radius_meters) / earth_radius_m
    points = []

    for i in range(max(8, int(segments))):
        bearing = 2.0 * math.pi * i / max(8, int(segments))
        sin_lat2 = (
            math.sin(lat1) * math.cos(angular_distance)
            + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
        )
        lat2 = math.asin(max(-1.0, min(1.0, sin_lat2)))
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
            math.cos(angular_distance) - (math.sin(lat1) * math.sin(lat2)),
        )
        lon_deg = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
        lat_deg = math.degrees(lat2)
        points.append([lon_deg, lat_deg])

    if points:
        points.append(points[0])
    return points


def upsert_restaurant_geofences(restaurant_id, location):
    if not LOCATION_GEOFENCE_COLLECTION_NAME:
        return False

    lat = _coerce_float(location.get('lat') if isinstance(location, dict) else None)
    lon = _coerce_float(location.get('lon') if isinstance(location, dict) else None)
    if lat is None or lon is None:
        return False

    client = _get_location_client()
    if client is None:
        return False

    entries = []
    for event_name, radius_m in get_geofence_radii_meters().items():
        zone_name = EVENT_ZONE_MAP.get(event_name)
        entries.append({
            'GeofenceId': f"{restaurant_id}|{event_name}",
            'Geometry': {
                'Polygon': [_build_circle_polygon(lat, lon, radius_m)],
            },
            'GeofenceProperties': {
                'restaurant_id': str(restaurant_id),
                'arrival_event': str(event_name),
                'arrival_zone': str(zone_name or ''),
            },
        })

    try:
        result = client.batch_put_geofence(
            CollectionName=LOCATION_GEOFENCE_COLLECTION_NAME,
            Entries=entries,
        )
        errors = result.get('Errors') or []
        if errors:
            print(f"Geofence upsert returned errors for {restaurant_id}: {errors}")
            return False
        return True
    except Exception as e:
        print(f"Failed to upsert geofences for {restaurant_id}: {e}")
        return False


def delete_restaurant_geofences(restaurant_id):
    if not LOCATION_GEOFENCE_COLLECTION_NAME:
        return False

    client = _get_location_client()
    if client is None:
        return False

    geofence_ids = [f"{restaurant_id}|{event_name}" for event_name in ZONE_EVENT_MAP.values()]
    try:
        result = client.batch_delete_geofence(
            CollectionName=LOCATION_GEOFENCE_COLLECTION_NAME,
            GeofenceIds=geofence_ids,
        )
        errors = result.get('Errors') or []
        if errors:
            print(f"Geofence delete returned errors for {restaurant_id}: {errors}")
            return False
        return True
    except Exception as e:
        print(f"Failed to delete geofences for {restaurant_id}: {e}")
        return False


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


def _coerce_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN check
        return None
    return number


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

    # Normalize coordinates for frontend clients that expect top-level fields.
    # Source-of-truth remains location.lat/lon in storage.
    location = response_item.get('location')
    location_lat = location.get('lat') if isinstance(location, dict) else None
    location_lon = location.get('lon') if isinstance(location, dict) else None

    latitude = _coerce_float(response_item.get('latitude'))
    longitude = _coerce_float(response_item.get('longitude'))
    if latitude is None:
        latitude = _coerce_float(location_lat)
    if longitude is None:
        longitude = _coerce_float(location_lon)

    if latitude is not None:
        response_item['latitude'] = latitude
    if longitude is not None:
        response_item['longitude'] = longitude

    response_item['restaurant_images'] = image_urls
    if image_urls:
        if not response_item.get('image_url'):
            response_item['image_url'] = image_urls[0]
        if len(image_urls) > 1 and not response_item.get('banner_image_url'):
            response_item['banner_image_url'] = image_urls[1]

    return response_item
