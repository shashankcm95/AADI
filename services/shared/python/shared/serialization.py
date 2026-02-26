"""
JSON serialization utilities — single source of truth.

Handles Decimal→float conversion for DynamoDB values and provides
a standard `make_response()` for all Lambda handlers.
"""

import json
from decimal import Decimal

from shared.cors import cors_headers


def decimal_default(obj):
    """JSON serializer for Decimal values from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def make_response(status_code, body, event=None):
    """Build a Lambda response with CORS headers and JSON body.

    Args:
        status_code: HTTP status code (200, 400, 500, etc.)
        body: dict to serialize as JSON
        event: optional API Gateway event for dynamic CORS origin matching
    """
    return {
        'statusCode': status_code,
        'headers': cors_headers(event),
        'body': json.dumps(body, default=decimal_default),
    }
