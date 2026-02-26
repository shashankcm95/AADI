"""Shared DynamoDB references and utility functions for the orders service.

All handler modules import table references from here.
Tests patch these module-level variables to inject in-memory mocks.
"""
import os
import json
import boto3
from decimal import Decimal
from typing import Dict, Any, Optional

from shared.cors import get_cors_origin, cors_headers, CORS_HEADERS
from shared.serialization import decimal_default

import capacity

# ---------------------------------------------------------------------------
# Input validation allowlists
# ---------------------------------------------------------------------------
VALID_VICINITY_EVENTS = {'5_MIN_OUT', 'PARKING', 'AT_DOOR', 'EXIT_VICINITY'}
VALID_RESTAURANT_STATUSES = {'IN_PROGRESS', 'READY', 'FULFILLING', 'COMPLETED'}

# ---------------------------------------------------------------------------
# DynamoDB table references (mocked in tests)
# ---------------------------------------------------------------------------
dynamodb = boto3.resource('dynamodb')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE')
CAPACITY_TABLE = os.environ.get('CAPACITY_TABLE')
RESTAURANT_CONFIG_TABLE = os.environ.get('RESTAURANT_CONFIG_TABLE')
IDEMPOTENCY_TABLE = os.environ.get('IDEMPOTENCY_TABLE')
GEOFENCE_EVENTS_TABLE = os.environ.get('GEOFENCE_EVENTS_TABLE')

orders_table = dynamodb.Table(ORDERS_TABLE) if ORDERS_TABLE else None
capacity_table = dynamodb.Table(CAPACITY_TABLE) if CAPACITY_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None
idempotency_table = dynamodb.Table(IDEMPOTENCY_TABLE) if IDEMPOTENCY_TABLE else None
geofence_events_table = dynamodb.Table(GEOFENCE_EVENTS_TABLE) if GEOFENCE_EVENTS_TABLE else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status_code, body, event=None):
    """Helper to build a response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': cors_headers(event),
        'body': json.dumps(body, default=str)
    }


def get_auth_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract auth claims from API Gateway event (HTTP API v2 or REST v1)."""
    try:
        return event['requestContext']['authorizer']['jwt']['claims']
    except (KeyError, TypeError):
        try:
            return event['requestContext']['authorizer']['claims']
        except (KeyError, TypeError):
            return {}


def get_user_role(event: Dict[str, Any], default: str = "") -> str:
    """
    Return normalized role from claims.
    Defaults to empty role for fail-closed authorization handling.
    """
    claims = get_auth_claims(event)
    return claims.get('custom:role') or claims.get('role') or default


def get_assigned_restaurant_id(event: Dict[str, Any]) -> Optional[str]:
    """Return the restaurant id bound to a restaurant_admin account, if present."""
    claims = get_auth_claims(event)
    return claims.get('custom:restaurant_id') or claims.get('restaurant_id')


def get_customer_id(event):
    """
    Extract customer ID from Cognito auth claims.
    Falls back to 'cust_demo' only if auth is missing (local testing).
    """
    claims = get_auth_claims(event)
    return claims.get('sub')


def release_capacity_slot(session: Dict[str, Any]) -> None:
    """
    Release a capacity slot if one was reserved for this session.
    Safe to call even if no slot was reserved (no-ops gracefully).
    """
    if not capacity_table:
        return

    window_start = session.get('capacity_window_start')
    if window_start is None:
        return  # No capacity slot was ever reserved

    destination_id = session.get('destination_id', session.get('restaurant_id'))
    capacity.release_slot(
        table=capacity_table,
        destination_id=destination_id,
        window_start=int(window_start),
    )
