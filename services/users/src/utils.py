import json
import os
import boto3
from decimal import Decimal

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')

USERS_TABLE = os.environ.get('USERS_TABLE')
USER_POOL_ID = os.environ.get('USER_POOL_ID')

users_table = dynamodb.Table(USERS_TABLE) if USERS_TABLE else None

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
}

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def get_user_claims(event):
    """Extract user claims from the event (Cognito JWT)."""
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        return {
            'role': claims.get('custom:role') or claims.get('role'),
            'user_id': claims.get('sub'),
            'username': claims.get('cognito:username') or claims.get('username'),
            'email': claims.get('email')
        }
    except (KeyError, TypeError):
        return {}

def json_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=decimal_default)
    }
