import os
import boto3

from shared.auth import get_user_claims  # noqa: F401 — re-exported
from shared.serialization import make_response  # noqa: F401 — re-exported

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

USERS_TABLE = os.environ.get('USERS_TABLE')

users_table = dynamodb.Table(USERS_TABLE) if USERS_TABLE else None
