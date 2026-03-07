"""
Users Service Router Tests

Tests the lambda_handler dispatch logic in app.py:
  - Health endpoint
  - Route dispatch to correct handler
  - Unknown route → 404
  - Exception catch-all → 500
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app


def _make_event(route_key):
    return {
        'routeKey': route_key,
        'requestContext': {
            'authorizer': {
                'jwt': {'claims': {'sub': 'user_test'}}
            }
        },
        'headers': {'origin': 'http://localhost:5173'},
    }


def test_health_endpoint():
    """GET /v1/users/health → 200 with healthy status."""
    event = _make_event('GET /v1/users/health')
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['status'] == 'healthy'
    assert body['service'] == 'users'


def test_get_profile_routes_to_handler():
    """GET /v1/users/me → dispatches to users.get_profile."""
    with patch('handlers.users.get_profile') as mock_handler:
        mock_handler.return_value = {'statusCode': 200, 'body': '{}'}
        event = _make_event('GET /v1/users/me')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        mock_handler.assert_called_once_with(event)


def test_update_profile_routes_to_handler():
    """PUT /v1/users/me → dispatches to users.update_profile."""
    with patch('handlers.users.update_profile') as mock_handler:
        mock_handler.return_value = {'statusCode': 200, 'body': '{}'}
        event = _make_event('PUT /v1/users/me')
        event['body'] = json.dumps({'name': 'Test'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        mock_handler.assert_called_once_with(event)


def test_avatar_upload_url_routes_to_handler():
    """POST /v1/users/me/avatar/upload-url → dispatches to users.create_avatar_upload_url."""
    with patch('handlers.users.create_avatar_upload_url') as mock_handler:
        mock_handler.return_value = {'statusCode': 200, 'body': '{}'}
        event = _make_event('POST /v1/users/me/avatar/upload-url')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        mock_handler.assert_called_once_with(event)


def test_unknown_route_returns_404():
    """Unknown route → 404."""
    event = _make_event('GET /v1/users/unknown')
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 404
    body = json.loads(resp['body'])
    assert 'Not Found' in body.get('error', '')


def test_handler_exception_returns_500():
    """Unhandled exception → 500 with generic message."""
    with patch('handlers.users.get_profile') as mock_handler:
        mock_handler.side_effect = RuntimeError("Unexpected failure")
        event = _make_event('GET /v1/users/me')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 500
        body = json.loads(resp['body'])
        assert 'Internal server error' in body.get('error', '')
