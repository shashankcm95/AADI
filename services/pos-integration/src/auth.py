"""
POS API Key Authentication Module

POS systems authenticate via the X-POS-API-Key header.
Each key maps to a restaurant_id and a set of permissions.
"""

import os
import logging
import boto3
import time
from typing import Optional, Dict, Any

logger = logging.getLogger("pos.auth")

dynamodb = boto3.resource('dynamodb')
POS_API_KEYS_TABLE = os.environ.get('POS_API_KEYS_TABLE')

if not POS_API_KEYS_TABLE:
    logger.warning("POS_API_KEYS_TABLE env var not set — all API key validation will fail")

keys_table = dynamodb.Table(POS_API_KEYS_TABLE) if POS_API_KEYS_TABLE else None


def validate_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Look up an API key in DynamoDB.
    Returns key record with restaurant_id and permissions, or None if invalid.
    """
    if not api_key or not keys_table:
        return None

    try:
        resp = keys_table.get_item(Key={'api_key': api_key})
        item = resp.get('Item')

        if not item:
            return None

        # Check if key is expired
        ttl = item.get('ttl')
        if ttl and int(ttl) < int(time.time()):
            return None

        return {
            'api_key': item['api_key'],
            'restaurant_id': item['restaurant_id'],
            'pos_system': item.get('pos_system', 'generic'),
            'permissions': item.get('permissions', []),  # Fail-closed: no permissions if unset
            'created_at': item.get('created_at'),
        }
    except Exception as e:
        logger.error("api_key_lookup_error", extra={"error": str(e)}, exc_info=True)
        return None


def require_permission(key_record: Dict[str, Any], permission: str) -> bool:
    """
    Check if a key has a specific permission.
    Permissions follow the format: 'resource:action' (e.g., 'orders:write', 'menu:read')
    """
    permissions = key_record.get('permissions', [])
    # Wildcard check
    if '*' in permissions:
        return True
    return permission in permissions


def authenticate_request(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and validate the API key from the request headers.
    Returns the key record or None.
    """
    headers = event.get('headers', {})
    # Headers are lowercased by API Gateway
    api_key = headers.get('x-pos-api-key') or headers.get('X-POS-API-Key')

    if not api_key:
        return None

    return validate_key(api_key)
