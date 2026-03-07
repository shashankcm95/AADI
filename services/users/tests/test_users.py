"""
Unit tests for the users service handlers.

Migrated from unittest.TestCase to pytest style for consistency
with the rest of the codebase.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from handlers import users


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_users_table():
    """Patch users.users_table with a MagicMock, restore after test."""
    mock_table = MagicMock()
    original = users.users_table
    users.users_table = mock_table
    yield mock_table
    users.users_table = original


@pytest.fixture
def mock_s3():
    """Patch users.s3_client with a MagicMock, restore after test."""
    mock_client = MagicMock()
    original = users.s3_client
    users.s3_client = mock_client
    yield mock_client
    users.s3_client = original


def _make_event(body=None):
    return {
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'user123'}}}
        },
        'headers': {'origin': 'http://localhost:5173'},
        'body': json.dumps(body) if body is not None else None,
    }


# =============================================================================
# get_profile
# =============================================================================

def test_get_profile_success(mock_users_table, mock_s3):
    event = _make_event()
    mock_users_table.get_item.return_value = {
        'Item': {'user_id': 'user123', 'name': 'John Doe'}
    }

    response = users.get_profile(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['name'] == 'John Doe'


def test_get_profile_with_avatar_key_returns_picture_url(mock_users_table, mock_s3):
    event = _make_event()
    mock_users_table.get_item.return_value = {
        'Item': {'user_id': 'user123', 'picture': 'avatars/user123-1700000000.jpg'}
    }
    mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

    with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
        response = users.get_profile(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['picture'] == 'avatars/user123-1700000000.jpg'
    assert body['picture_url'] == 'https://signed.example/avatar.jpg'
    mock_s3.generate_presigned_url.assert_called_with(
        'get_object',
        Params={'Bucket': 'test-bucket', 'Key': 'avatars/user123-1700000000.jpg'},
        ExpiresIn=900,
    )


def test_get_profile_normalizes_legacy_s3_url_picture(mock_users_table, mock_s3):
    event = _make_event()
    mock_users_table.get_item.return_value = {
        'Item': {
            'user_id': 'user123',
            'picture': 'https://test-bucket.s3.us-east-1.amazonaws.com/avatars/user123-1700000000.jpg',
        }
    }
    mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

    with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
        response = users.get_profile(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['picture'] == 'avatars/user123-1700000000.jpg'
    assert body['picture_url'] == 'https://signed.example/avatar.jpg'


def test_get_profile_not_found(mock_users_table, mock_s3):
    event = _make_event()
    mock_users_table.get_item.return_value = {}  # No Item

    response = users.get_profile(event)

    assert response['statusCode'] == 404


def test_get_profile_missing_user_id(mock_users_table, mock_s3):
    """Missing user_id in claims → 401."""
    event = {
        'requestContext': {
            'authorizer': {'jwt': {'claims': {}}}  # No 'sub'
        },
        'headers': {'origin': 'http://localhost:5173'},
    }
    response = users.get_profile(event)
    assert response['statusCode'] == 401


def test_get_profile_table_is_none(mock_users_table, mock_s3):
    """users_table is None → 500."""
    original = users.users_table
    users.users_table = None
    try:
        event = _make_event()
        response = users.get_profile(event)
        assert response['statusCode'] == 500
        assert 'Database' in json.loads(response['body']).get('error', '')
    finally:
        users.users_table = original


def test_get_profile_dynamodb_exception(mock_users_table, mock_s3):
    """DynamoDB exception on get_item → 500."""
    mock_users_table.get_item.side_effect = Exception("DDB timeout")
    event = _make_event()
    response = users.get_profile(event)
    assert response['statusCode'] == 500


# =============================================================================
# update_profile
# =============================================================================

def test_update_profile_success(mock_users_table, mock_s3):
    event = _make_event({'name': 'Jane Doe', 'phone_number': '555-1234'})
    mock_users_table.update_item.return_value = {
        'Attributes': {'user_id': 'user123', 'name': 'Jane Doe'}
    }

    response = users.update_profile(event)

    assert response['statusCode'] == 200

    # Verify update call
    args = mock_users_table.update_item.call_args[1]
    assert args['Key'] == {'user_id': 'user123'}
    assert '#name = :name' in args['UpdateExpression']
    assert '#phone_number = :phone_number' in args['UpdateExpression']
    assert args['ExpressionAttributeValues'][':name'] == 'Jane Doe'
    # Existence guard must be present
    assert args['ConditionExpression'] == 'attribute_exists(user_id)'


def test_update_profile_invalid_fields_ignored(mock_users_table, mock_s3):
    event = _make_event({'role': 'admin', 'name': 'Hacker'})
    mock_users_table.update_item.return_value = {}

    users.update_profile(event)

    args = mock_users_table.update_item.call_args[1]
    assert '#name = :name' in args['UpdateExpression']
    for key in args['ExpressionAttributeNames'].keys():
        assert args['ExpressionAttributeNames'][key] != 'role'


def test_update_profile_not_found(mock_users_table, mock_s3):
    """update_item raises ConditionalCheckFailedException → 404."""
    event = _make_event({'name': 'Ghost'})
    error = ClientError(
        {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'x'}},
        'UpdateItem',
    )
    mock_users_table.update_item.side_effect = error

    response = users.update_profile(event)

    assert response['statusCode'] == 404


def test_update_profile_picture_valid(mock_users_table, mock_s3):
    event = _make_event({'picture': 'avatars/user123-1700000000.jpg'})
    mock_users_table.update_item.return_value = {
        'Attributes': {'user_id': 'user123', 'picture': 'avatars/user123-1700000000.jpg'}
    }
    mock_s3.generate_presigned_url.return_value = 'https://signed.example/avatar.jpg'

    with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
        response = users.update_profile(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['picture'] == 'avatars/user123-1700000000.jpg'
    assert body['picture_url'] == 'https://signed.example/avatar.jpg'

    args = mock_users_table.update_item.call_args[1]
    assert '#picture = :picture' in args['UpdateExpression']


def test_update_profile_picture_wrong_user_rejected(mock_users_table, mock_s3):
    """picture key belonging to another user must be rejected."""
    event = _make_event({'picture': 'avatars/otheruser-1700000000.jpg'})

    response = users.update_profile(event)

    assert response['statusCode'] == 400
    mock_users_table.update_item.assert_not_called()


def test_update_profile_picture_invalid_format_rejected(mock_users_table, mock_s3):
    """Malformed picture key must be rejected."""
    event = _make_event({'picture': 'https://evil.com/malware.jpg'})

    response = users.update_profile(event)

    assert response['statusCode'] == 400
    mock_users_table.update_item.assert_not_called()


def test_update_profile_missing_user_id(mock_users_table, mock_s3):
    """Missing user_id → 401."""
    event = {
        'requestContext': {
            'authorizer': {'jwt': {'claims': {}}}
        },
        'headers': {'origin': 'http://localhost:5173'},
        'body': json.dumps({'name': 'Test'}),
    }
    response = users.update_profile(event)
    assert response['statusCode'] == 401


def test_update_profile_no_body(mock_users_table, mock_s3):
    """Missing body → 400."""
    event = _make_event()
    event['body'] = None
    response = users.update_profile(event)
    assert response['statusCode'] == 400
    assert 'Missing' in json.loads(response['body']).get('error', '')


def test_update_profile_invalid_json(mock_users_table, mock_s3):
    """Invalid JSON → 400."""
    event = _make_event()
    event['body'] = '{invalid_json'
    response = users.update_profile(event)
    assert response['statusCode'] == 400
    assert 'Invalid JSON' in json.loads(response['body']).get('error', '')


def test_update_profile_name_not_string(mock_users_table, mock_s3):
    """name as non-string → 400."""
    event = _make_event({'name': 12345})
    response = users.update_profile(event)
    assert response['statusCode'] == 400
    assert 'name' in json.loads(response['body']).get('error', '').lower()


def test_update_profile_name_empty(mock_users_table, mock_s3):
    """Empty name → 400."""
    event = _make_event({'name': '   '})
    response = users.update_profile(event)
    assert response['statusCode'] == 400


def test_update_profile_name_too_long(mock_users_table, mock_s3):
    """Name > 255 chars → 400."""
    event = _make_event({'name': 'A' * 256})
    response = users.update_profile(event)
    assert response['statusCode'] == 400


def test_update_profile_phone_too_long(mock_users_table, mock_s3):
    """phone_number > 30 chars → 400."""
    event = _make_event({'phone_number': '1' * 31})
    response = users.update_profile(event)
    assert response['statusCode'] == 400


def test_update_profile_no_valid_fields(mock_users_table, mock_s3):
    """Only invalid fields → 400."""
    event = _make_event({'role': 'admin', 'email': 'hack@evil.com'})
    response = users.update_profile(event)
    assert response['statusCode'] == 400
    assert 'No valid fields' in json.loads(response['body']).get('error', '')


def test_update_profile_dynamodb_exception(mock_users_table, mock_s3):
    """General DynamoDB exception → 500."""
    event = _make_event({'name': 'Valid Name'})
    mock_users_table.update_item.side_effect = Exception("DDB timeout")
    response = users.update_profile(event)
    assert response['statusCode'] == 500


# =============================================================================
# create_avatar_upload_url
# =============================================================================

def test_create_avatar_upload_url(mock_users_table, mock_s3):
    mock_s3.generate_presigned_url.return_value = (
        'https://s3.amazonaws.com/test-bucket/avatars/user123.jpg'
    )

    event = _make_event({'content_type': 'image/jpeg'})

    with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
        response = users.create_avatar_upload_url(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['upload_url'] == 'https://s3.amazonaws.com/test-bucket/avatars/user123.jpg'
    assert 's3_key' in body
    assert body['s3_key'].startswith('avatars/user123-')
    assert body['s3_key'].endswith('.jpg')
    assert body['expires_in'] == 300
    assert 'public_url' not in body


def test_create_avatar_upload_url_missing_user_id(mock_users_table, mock_s3):
    """Missing user_id → 401."""
    event = {
        'requestContext': {
            'authorizer': {'jwt': {'claims': {}}}
        },
        'headers': {'origin': 'http://localhost:5173'},
    }
    response = users.create_avatar_upload_url(event)
    assert response['statusCode'] == 401


def test_create_avatar_upload_url_no_bucket(mock_users_table, mock_s3):
    """AVATARS_BUCKET_NAME not set → 500."""
    event = _make_event({'content_type': 'image/jpeg'})
    with patch.dict(os.environ, {}, clear=True):
        # Remove AVATARS_BUCKET_NAME from env
        os.environ.pop('AVATARS_BUCKET_NAME', None)
        response = users.create_avatar_upload_url(event)
    assert response['statusCode'] == 500
    assert 'Storage' in json.loads(response['body']).get('error', '')


def test_create_avatar_upload_url_s3_exception(mock_users_table, mock_s3):
    """S3 presigned URL exception → 500."""
    event = _make_event({'content_type': 'image/jpeg'})
    mock_s3.generate_presigned_url.side_effect = Exception("S3 error")
    with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
        response = users.create_avatar_upload_url(event)
    assert response['statusCode'] == 500
