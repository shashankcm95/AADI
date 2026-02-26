"""Restaurant configuration handlers."""
import json
import time
import uuid

from utils import (
    CORS_HEADERS,
    DEFAULT_DISPATCH_TRIGGER_ZONE,
    DEFAULT_ZONE_LABELS,
    DEFAULT_ZONE_DISTANCES_M,
    EVENT_ZONE_MAP,
    GLOBAL_CONFIG_ID,
    ZONE_EVENT_MAP,
    config_table,
    decimal_default,
    get_global_zone_labels,
    get_global_zone_distances,
    get_user_claims,
    make_response,
    normalize_dispatch_trigger_event,
    normalize_dispatch_trigger_zone,
    restaurants_table,
    upsert_restaurant_geofences,
)

# ── Constants ──
VALID_POS_PROVIDERS = {'square', 'toast', 'clover', 'custom'}
MAX_POS_CONNECTIONS = 5
VALID_DISPATCH_TRIGGER_EVENTS = set(ZONE_EVENT_MAP.values())
VALID_DISPATCH_TRIGGER_ZONES = set(ZONE_EVENT_MAP.keys())


def _mask_secret(secret):
    """Mask a webhook secret for safe display: ***…last4."""
    if not secret or len(secret) < 8:
        return '***'
    return f"***…{secret[-4:]}"


def _mask_pos_connections(connections):
    """Return POS connections with secrets masked."""
    if not connections:
        return []
    masked = []
    for conn in connections:
        c = dict(conn)
        if 'webhook_secret' in c:
            c['webhook_secret'] = _mask_secret(c['webhook_secret'])
        masked.append(c)
    return masked


def _validate_pos_connections(connections):
    """Validate POS connections list. Returns (cleaned, error_msg)."""
    if not isinstance(connections, list):
        return None, 'pos_connections must be a list'
    if len(connections) > MAX_POS_CONNECTIONS:
        return None, f'Maximum {MAX_POS_CONNECTIONS} POS connections allowed'

    cleaned = []
    for i, conn in enumerate(connections):
        if not isinstance(conn, dict):
            return None, f'pos_connections[{i}] must be an object'

        url = conn.get('webhook_url', '')
        if url and not url.startswith('https://'):
            return None, f'pos_connections[{i}].webhook_url must use HTTPS'

        provider = conn.get('provider', 'custom')
        if provider not in VALID_POS_PROVIDERS:
            return None, f'pos_connections[{i}].provider must be one of: {", ".join(sorted(VALID_POS_PROVIDERS))}'

        cleaned.append({
            'connection_id': conn.get('connection_id') or str(uuid.uuid4()),
            'label': conn.get('label', f'{provider.title()} POS'),
            'provider': provider,
            'webhook_url': url,
            'webhook_secret': conn.get('webhook_secret', ''),
            'enabled': bool(conn.get('enabled', True)),
            'created_at': conn.get('created_at') or int(time.time()),
        })
    return cleaned, None


def _parse_dispatch_selection(item):
    zone = normalize_dispatch_trigger_zone(item.get('dispatch_trigger_zone'))
    if zone is None:
        zone = normalize_dispatch_trigger_zone(item.get('dispatch_trigger_event'))
    if zone is None:
        zone = DEFAULT_DISPATCH_TRIGGER_ZONE
    return zone, ZONE_EVENT_MAP[zone]


def _parse_zone_distance(value):
    try:
        meters = int(value)
    except (TypeError, ValueError):
        return None
    if meters < 10 or meters > 50_000:
        return None
    return meters


def _normalize_zone_distance_update(payload, current_zone_distances):
    if payload is None:
        return dict(current_zone_distances), False, None
    if not isinstance(payload, dict):
        return None, False, 'zone_distances_m must be an object'

    normalized = dict(current_zone_distances)
    touched = False
    for zone in DEFAULT_ZONE_DISTANCES_M:
        candidate = payload.get(zone)
        if candidate is None:
            candidate = payload.get(ZONE_EVENT_MAP[zone])
        if candidate is None:
            continue

        parsed = _parse_zone_distance(candidate)
        if parsed is None:
            return None, False, f'{zone} must be an integer between 10 and 50000 meters'
        normalized[zone] = parsed
        touched = True
    return normalized, touched, None


def _normalize_zone_label_update(payload, current_zone_labels):
    if payload is None:
        return dict(current_zone_labels), False, None
    if not isinstance(payload, dict):
        return None, False, 'zone_labels must be an object'

    normalized = dict(current_zone_labels)
    touched = False
    for zone in DEFAULT_ZONE_LABELS:
        candidate = payload.get(zone)
        if candidate is None:
            continue

        label = str(candidate).strip()
        if not label:
            return None, False, f'{zone} label cannot be empty'
        normalized[zone] = label[:48]
        touched = True
    return normalized, touched, None


def _validate_global_updates(zone_distances_touched, zone_labels_touched):
    if zone_distances_touched or zone_labels_touched:
        return None
    return 'Provide at least one field to update: zone_distances_m or zone_labels'


def _resync_all_restaurant_geofences():
    if not restaurants_table:
        return {'attempted': 0, 'updated': 0, 'failed': 0}

    attempted = 0
    updated = 0
    failed = 0

    scan_kwargs = {}
    while True:
        response = restaurants_table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            restaurant_id = item.get('restaurant_id')
            location = item.get('location')
            if not restaurant_id:
                continue
            attempted += 1
            if upsert_restaurant_geofences(restaurant_id, location):
                updated += 1
            else:
                failed += 1

        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break
        scan_kwargs['ExclusiveStartKey'] = last_key

    return {'attempted': attempted, 'updated': updated, 'failed': failed}


def get_config(event, restaurant_id):
    """Get capacity + POS configuration for a restaurant."""
    if not config_table:
        return make_response(500, {'error': 'Config table not configured'})

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return make_response(403, {'error': 'Access denied'})

    try:
        resp = config_table.get_item(Key={'restaurant_id': restaurant_id})
        item = resp.get('Item', {})
        config = item.get('configuration', {})

        zone_distances = get_global_zone_distances()
        dispatch_zone, dispatch_event = _parse_dispatch_selection(item)

        response_data = {
            'max_concurrent_orders': int(item.get('max_concurrent_orders', 10)),
            'capacity_window_seconds': int(item.get('capacity_window_seconds', 300)),
            'dispatch_trigger_zone': dispatch_zone,
            'dispatch_trigger_event': dispatch_event,
            'zone_distances_m': zone_distances,
            'zone_labels': get_global_zone_labels(),
            'operating_hours': config.get('operating_hours'),
            'timezone': config.get('timezone'),
            # POS fields
            'pos_enabled': bool(item.get('pos_enabled', False)),
            'pos_connections': _mask_pos_connections(item.get('pos_connections', [])),
        }

        return make_response(200, response_data)
    except Exception as e:
        print(f"Get Config Error: {e}")
        return make_response(500, {'error': str(e)})


def update_config(event, restaurant_id):
    """Update capacity + POS configuration."""
    if not config_table:
        return make_response(500, {'error': 'Config table not configured'})

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return make_response(403, {'error': 'Access denied'})

    try:
        body = json.loads(event.get('body', '{}'))

        max_concurrent = body.get('max_concurrent_orders')
        window_seconds = body.get('capacity_window_seconds')
        dispatch_trigger_event = body.get('dispatch_trigger_event')
        dispatch_trigger_zone = body.get('dispatch_trigger_zone')

        update_expr_parts = []
        expr_values = {}

        if max_concurrent is not None:
            update_expr_parts.append("max_concurrent_orders = :m")
            expr_values[':m'] = int(max_concurrent)

        if window_seconds is not None:
            update_expr_parts.append("capacity_window_seconds = :w")
            expr_values[':w'] = int(window_seconds)

        selected_zone = None
        selected_event = None

        if dispatch_trigger_zone is not None:
            selected_zone = normalize_dispatch_trigger_zone(dispatch_trigger_zone)
            if not selected_zone:
                allowed = ', '.join(sorted(VALID_DISPATCH_TRIGGER_ZONES))
                return make_response(400, {'error': f'dispatch_trigger_zone must be one of: {allowed}'})
            selected_event = ZONE_EVENT_MAP[selected_zone]

        if dispatch_trigger_event is not None:
            normalized_trigger = normalize_dispatch_trigger_event(dispatch_trigger_event)
            if not normalized_trigger:
                allowed = ', '.join(sorted(VALID_DISPATCH_TRIGGER_EVENTS))
                return make_response(400, {'error': f'dispatch_trigger_event must be one of: {allowed}'})
            event_zone = EVENT_ZONE_MAP[normalized_trigger]
            if selected_zone and selected_zone != event_zone:
                return make_response(400, {'error': 'dispatch_trigger_zone and dispatch_trigger_event do not match'})
            selected_zone = event_zone
            selected_event = normalized_trigger

        if selected_zone is not None:
            update_expr_parts.append("dispatch_trigger_zone = :dtz")
            update_expr_parts.append("dispatch_trigger_event = :dte")
            expr_values[':dtz'] = selected_zone
            expr_values[':dte'] = selected_event or ZONE_EVENT_MAP[selected_zone]

        # ── POS fields ──
        pos_enabled = body.get('pos_enabled')
        if pos_enabled is not None:
            update_expr_parts.append("pos_enabled = :pe")
            expr_values[':pe'] = bool(pos_enabled)

        pos_connections = body.get('pos_connections')
        if pos_connections is not None:
            # When client sends masked secrets (***…xxxx), preserve existing secrets
            existing = {}
            if any(c.get('webhook_secret', '').startswith('***') for c in pos_connections if isinstance(c, dict)):
                resp = config_table.get_item(Key={'restaurant_id': restaurant_id})
                for c in resp.get('Item', {}).get('pos_connections', []):
                    existing[c.get('connection_id')] = c.get('webhook_secret', '')

            # Restore masked secrets from existing data
            for conn in pos_connections:
                if isinstance(conn, dict):
                    secret = conn.get('webhook_secret', '')
                    if secret.startswith('***') and conn.get('connection_id') in existing:
                        conn['webhook_secret'] = existing[conn['connection_id']]

            cleaned, err = _validate_pos_connections(pos_connections)
            if err:
                return make_response(400, {'error': err})
            update_expr_parts.append("pos_connections = :pc")
            expr_values[':pc'] = cleaned

        if not update_expr_parts:
            return make_response(400, {'error': 'No valid fields to update'})

        update_expr_parts.append("updated_at = :u")
        expr_values[':u'] = int(time.time())

        config_table.update_item(
            Key={'restaurant_id': restaurant_id},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeValues=expr_values
        )

        return make_response(200, {'message': 'Configuration updated'})

    except Exception as e:
        print(f"Update Config Error: {e}")
        return make_response(500, {'error': str(e)})


def get_global_config(event):
    """Get platform-wide zone distance settings (admin only)."""
    if not config_table:
        return make_response(500, {'error': 'Config table not configured'})

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return make_response(403, {'error': 'Access denied'})

    zone_distances = get_global_zone_distances()
    return make_response(200, {
        'zone_distances_m': zone_distances,
        'zone_labels': get_global_zone_labels(),
        'zone_event_map': ZONE_EVENT_MAP,
        'default_dispatch_trigger_zone': DEFAULT_DISPATCH_TRIGGER_ZONE,
    })


def update_global_config(event):
    """Update platform-wide zone distances and resync AWS geofences (admin only)."""
    if not config_table:
        return make_response(500, {'error': 'Config table not configured'})

    claims = get_user_claims(event)
    if claims.get('role') != 'admin':
        return make_response(403, {'error': 'Access denied'})

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        return make_response(400, {'error': 'Invalid JSON body'})

    now = int(time.time())
    existing = config_table.get_item(Key={'restaurant_id': GLOBAL_CONFIG_ID}).get('Item', {})
    created_at = int(existing.get('created_at', now))
    current_zone_distances = dict(get_global_zone_distances())
    current_zone_labels = dict(get_global_zone_labels())

    raw_zone_distances = body.get('zone_distances_m')
    raw_zone_labels = body.get('zone_labels')

    if raw_zone_distances is None and raw_zone_labels is None and isinstance(body, dict):
        if any(k in DEFAULT_ZONE_DISTANCES_M or k in ZONE_EVENT_MAP.values() for k in body):
            raw_zone_distances = body

    normalized_zone_distances, distances_touched, distances_err = _normalize_zone_distance_update(
        raw_zone_distances,
        current_zone_distances,
    )
    if distances_err:
        return make_response(400, {'error': distances_err})

    normalized_zone_labels, labels_touched, labels_err = _normalize_zone_label_update(
        raw_zone_labels,
        current_zone_labels,
    )
    if labels_err:
        return make_response(400, {'error': labels_err})

    global_err = _validate_global_updates(distances_touched, labels_touched)
    if global_err:
        return make_response(400, {'error': global_err})

    config_table.put_item(
        Item={
            'restaurant_id': GLOBAL_CONFIG_ID,
            'zone_distances_m': normalized_zone_distances,
            'zone_labels': normalized_zone_labels,
            'created_at': created_at,
            'updated_at': now,
        }
    )

    sync_stats = _resync_all_restaurant_geofences()
    return make_response(200, {
        'message': 'Global zone configuration updated',
        'zone_distances_m': normalized_zone_distances,
        'zone_labels': normalized_zone_labels,
        'geofence_sync': sync_stats,
    })
