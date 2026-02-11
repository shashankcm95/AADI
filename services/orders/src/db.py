"""
Shared DynamoDB references and utility functions for the orders service.

All handler modules import table references from here.
Tests patch these module-level variables to inject in-memory mocks.
"""
import os
import json
import boto3
from decimal import Decimal
from typing import Dict, Any

import capacity

# ---------------------------------------------------------------------------
# CORS headers for all responses (API Gateway handles preflight)
# ---------------------------------------------------------------------------
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
}

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

orders_table = dynamodb.Table(ORDERS_TABLE) if ORDERS_TABLE else None
capacity_table = dynamodb.Table(CAPACITY_TABLE) if CAPACITY_TABLE else None
config_table = dynamodb.Table(RESTAURANT_CONFIG_TABLE) if RESTAURANT_CONFIG_TABLE else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def make_response(status_code, body):
    """Helper to build a response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str)
    }


def get_customer_id(event):
    """
    Extract customer ID from Cognito auth claims.
    Falls back to 'cust_demo' only if auth is missing (local testing).
    """
    try:
        # HTTP API (v2) format
        return event['requestContext']['authorizer']['jwt']['claims']['sub']
    except (KeyError, TypeError):
        try:
            # REST API (v1) format or other authorizers
            return event['requestContext']['authorizer']['claims']['sub']
        except (KeyError, TypeError):
            print("WARNING: No auth context found. Using 'cust_demo'.")
            return "cust_demo"


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
