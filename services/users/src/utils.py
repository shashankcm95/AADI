import json
import os
import boto3
from decimal import Decimal

from shared.cors import get_cors_origin, cors_headers, CORS_HEADERS
from shared.auth import get_user_claims
from shared.serialization import decimal_default, make_response

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')

USERS_TABLE = os.environ.get('USERS_TABLE')
USER_POOL_ID = os.environ.get('USER_POOL_ID')

users_table = dynamodb.Table(USERS_TABLE) if USERS_TABLE else None


def json_response(status_code, body):
    """Build response — delegates to shared make_response."""
    return make_response(status_code, body)
