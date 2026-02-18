"""Restaurant configuration handlers."""
import json
import time
import uuid

from utils import (
    CORS_HEADERS, decimal_default, get_user_claims,
    config_table,
)

# ── Constants ──
VALID_POS_PROVIDERS = {'square', 'toast', 'clover', 'custom'}
MAX_POS_CONNECTIONS = 5


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


def get_config(event, restaurant_id):
    """Get capacity + POS configuration for a restaurant."""
    if not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Config table not configured'})}

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

        response_data = {
            'max_concurrent_orders': int(item.get('max_concurrent_orders', 10)),
            'capacity_window_seconds': int(item.get('capacity_window_seconds', 300)),
            'operating_hours': config.get('operating_hours'),
            'timezone': config.get('timezone'),
            # POS fields
            'pos_enabled': bool(item.get('pos_enabled', False)),
            'pos_connections': _mask_pos_connections(item.get('pos_connections', [])),
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
    """Update capacity + POS configuration."""
    if not config_table:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Config table not configured'})}

    claims = get_user_claims(event)
    user_role = claims.get('role')
    user_restaurant_id = claims.get('restaurant_id')

    is_admin = user_role == 'admin'
    is_owner = user_role == 'restaurant_admin' and user_restaurant_id == restaurant_id

    if not (is_admin or is_owner):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    try:
        body = json.loads(event.get('body', '{}'))

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
                return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': err})}
            update_expr_parts.append("pos_connections = :pc")
            expr_values[':pc'] = cleaned

        if not update_expr_parts:
            return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'No valid fields to update'})}

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
