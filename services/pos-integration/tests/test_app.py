
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop("app", None)
sys.modules.pop("handlers", None)

import app

@pytest.fixture
def mock_auth_module():
    """Patch the auth module functions."""
    with patch.object(app, 'authenticate_request') as mock_auth, \
         patch.object(app, 'require_permission') as mock_perm:
        yield mock_auth, mock_perm

def test_routes_create_order(mock_auth_module, mock_db):
    mock_authenticate, mock_require = mock_auth_module
    
    # Setup Auth success
    mock_authenticate.return_value = {'restaurant_id': 'rest_1', 'permissions': ['orders:write']}
    mock_require.return_value = True
    
    event = {
        'routeKey': 'POST /v1/pos/orders',
        'headers': {'X-POS-API-Key': 'valid'},
        'body': json.dumps({'items': [], 'pos_order_ref': 'ref1'})
    }
    
    # Mock handler to isolate routing/auth logic
    with patch.object(app, 'handle_create_order') as mock_handler:
        mock_handler.return_value = {'statusCode': 201, 'body': '{}'}
        
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201
        
        # Verify Auth called
        mock_authenticate.assert_called_once()
        mock_require.assert_called_with(mock_authenticate.return_value, 'orders:write')
        mock_handler.assert_called_once()

def test_auth_missing_key(mock_auth_module, mock_db):
    mock_authenticate, _ = mock_auth_module
    mock_authenticate.return_value = None # Auth failed
    
    event = {'routeKey': 'GET /v1/pos/orders', 'headers': {}}
    
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 401
    assert json.loads(resp['body'])['error'] == 'Unauthorized'

def test_auth_forbidden(mock_auth_module, mock_db):
    mock_authenticate, mock_require = mock_auth_module
    mock_authenticate.return_value = {'restaurant_id': 'rest_1'}
    mock_require.return_value = False # Permission denied
    
    event = {'routeKey': 'POST /v1/pos/orders', 'body': '{}'}
    
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 403
    assert 'Forbidden' in resp['body']

def test_invalid_json(mock_auth_module, mock_db):
    mock_authenticate, _ = mock_auth_module
    mock_authenticate.return_value = {'restaurant_id': 'rest_1'}
    
    event = {
        'routeKey': 'POST /v1/pos/orders',
        'body': '{invalid_json'
    }
    
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 400
    assert 'Invalid JSON' in resp['body']

def test_unknown_route(mock_auth_module, mock_db):
    mock_authenticate, _ = mock_auth_module
    mock_authenticate.return_value = {'restaurant_id': 'rest_1'}

    event = {'routeKey': 'GET /v1/unknown', 'body': '{}'}

    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 404

def test_webhook_requires_orders_write_permission(mock_auth_module, mock_db):
    """Webhook route must enforce orders:write — keys with only menu:read cannot create orders."""
    mock_authenticate, mock_require = mock_auth_module
    mock_authenticate.return_value = {'restaurant_id': 'rest_1', 'permissions': ['menu:read']}
    mock_require.return_value = False

    event = {
        'routeKey': 'POST /v1/pos/webhook',
        'body': '{"event_type": "order.created", "webhook_id": "wh_test"}'
    }

    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 403
    mock_require.assert_called_with(mock_authenticate.return_value, 'orders:write')
