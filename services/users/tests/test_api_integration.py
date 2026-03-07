"""
API Integration Tests for Users Service

Tests exercise the full lambda_handler → router → handler → DB → response chain,
verifying routing, CORS headers, auth claims parsing, and error handling.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

import app
from handlers import users


def _make_event(route_key, body=None, user_id='user_123'):
    """Build a minimal API Gateway v2 event."""
    event = {
        'routeKey': route_key,
        'requestContext': {
            'authorizer': {
                'jwt': {'claims': {'sub': user_id}}
            }
        },
        'headers': {'origin': 'http://localhost:5173'},
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


@pytest.fixture
def mock_tables():
    """Patch users_table and s3_client, restore after test."""
    mock_table = MagicMock()
    mock_s3 = MagicMock()

    original_table = users.users_table
    original_s3 = users.s3_client

    users.users_table = mock_table
    users.s3_client = mock_s3

    yield {'users_table': mock_table, 's3': mock_s3}

    users.users_table = original_table
    users.s3_client = original_s3


# =============================================================================
# Health & Routing
# =============================================================================

class TestHealthAndRouting:
    def test_health_endpoint(self, mock_tables):
        event = _make_event('GET /v1/users/health')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['status'] == 'healthy'
        assert body['service'] == 'users'

    def test_unknown_route_returns_404(self, mock_tables):
        event = _make_event('GET /v1/users/unknown')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404

    def test_exception_returns_500(self, mock_tables):
        """Unhandled exception → 500."""
        with patch.object(users, 'get_profile', side_effect=Exception("Boom")):
            event = _make_event('GET /v1/users/me')
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
            body = json.loads(resp['body'])
            assert 'Internal server error' in body.get('error', '')


# =============================================================================
# Profile Lifecycle via lambda_handler
# =============================================================================

class TestProfileLifecycle:
    def test_get_update_get_flow(self, mock_tables):
        """Get profile → Update profile → Get updated profile."""
        table = mock_tables['users_table']

        # 1. Get profile (existing user)
        table.get_item.return_value = {
            'Item': {'user_id': 'user_123', 'name': 'Alice'}
        }
        event = _make_event('GET /v1/users/me')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['name'] == 'Alice'

        # 2. Update profile
        table.update_item.return_value = {
            'Attributes': {'user_id': 'user_123', 'name': 'Alice Updated', 'phone_number': '555-0001'}
        }
        event = _make_event('PUT /v1/users/me', body={'name': 'Alice Updated', 'phone_number': '555-0001'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['name'] == 'Alice Updated'

        # 3. Get updated profile
        table.get_item.return_value = {
            'Item': {'user_id': 'user_123', 'name': 'Alice Updated', 'phone_number': '555-0001'}
        }
        event = _make_event('GET /v1/users/me')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['name'] == 'Alice Updated'
        assert body['phone_number'] == '555-0001'


# =============================================================================
# Avatar Upload Flow via lambda_handler
# =============================================================================

class TestAvatarUploadFlow:
    def test_request_upload_url_and_update_picture(self, mock_tables):
        """Request presigned URL → Update profile with s3_key → Get profile → verify."""
        table = mock_tables['users_table']
        s3 = mock_tables['s3']

        # 1. Request upload URL
        s3.generate_presigned_url.return_value = 'https://s3.example.com/signed'
        event = _make_event('POST /v1/users/me/avatar/upload-url',
                            body={'content_type': 'image/jpeg'})
        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert 'upload_url' in body
        s3_key = body['s3_key']
        assert s3_key.startswith('avatars/user_123-')

        # 2. Update profile with the s3_key
        table.update_item.return_value = {
            'Attributes': {'user_id': 'user_123', 'picture': s3_key}
        }
        s3.generate_presigned_url.return_value = 'https://s3.example.com/view-signed'
        event = _make_event('PUT /v1/users/me', body={'picture': s3_key})
        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['picture'] == s3_key

        # 3. Get profile → verify picture_url
        table.get_item.return_value = {
            'Item': {'user_id': 'user_123', 'picture': s3_key}
        }
        s3.generate_presigned_url.return_value = 'https://s3.example.com/avatar-url'
        event = _make_event('GET /v1/users/me')
        with patch.dict(os.environ, {'AVATARS_BUCKET_NAME': 'test-bucket'}, clear=False):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body.get('picture_url') == 'https://s3.example.com/avatar-url'


# =============================================================================
# CORS Headers
# =============================================================================

class TestCORSHeaders:
    def test_success_response_includes_cors(self, mock_tables):
        event = _make_event('GET /v1/users/health')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

    def test_404_includes_cors(self, mock_tables):
        event = _make_event('GET /v1/users/nonexistent')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

    def test_500_includes_cors(self, mock_tables):
        with patch.object(users, 'get_profile', side_effect=RuntimeError("crash")):
            event = _make_event('GET /v1/users/me')
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
            assert 'Access-Control-Allow-Origin' in resp.get('headers', {})


# =============================================================================
# Auth Claims Extraction
# =============================================================================

class TestAuthClaimsExtraction:
    def test_sub_claim_maps_to_user_id(self, mock_tables):
        """Verify 'sub' claim from JWT correctly maps to user_id in handler."""
        table = mock_tables['users_table']
        table.get_item.return_value = {
            'Item': {'user_id': 'specific_user_42', 'name': 'Test'}
        }
        event = _make_event('GET /v1/users/me', user_id='specific_user_42')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # Verify the correct user was queried
        call_args = table.get_item.call_args[1]
        assert call_args['Key']['user_id'] == 'specific_user_42'
