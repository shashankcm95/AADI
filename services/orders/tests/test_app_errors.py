
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app
import db
from decimal import Decimal
from models import Session, OrderStatus

def test_handler_json_error():
    # Force an error in a handler to test the app.py catch-all
    with patch.object(app, 'create_order') as mock_create:
        mock_create.side_effect = Exception("Boom")
        event = {
            'routeKey': 'POST /v1/orders',
            'body': '{}',
            'requestContext': {
                'authorizer': {
                    'jwt': {
                        'claims': {'sub': 'cust_1', 'custom:role': 'customer'}
                    }
                }
            }
        }
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 500
        assert 'Internal server error' in resp['body']

def test_handler_routing_404():
    event = {'routeKey': 'GET /v1/unknown'}
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 404
    assert 'Route not found' in resp['body']

def test_decimal_default():
    """Verify decimal_default raises TypeError for non-Decimal types."""
    with pytest.raises(TypeError):
        db.decimal_default("string")
    
    assert db.decimal_default(Decimal("10.5")) == 10.5

def test_session_hydration():
    """Verify Session.from_ddb error paths."""
    # Test valid with minimal required fields
    item = {
        'order_id': 'o1', 
        'status': 'PENDING_NOT_SENT',
        'created_at': 100,
        'expires_at': 200,
        'destination_id': 'd1'
    }
    s = Session.from_ddb(item)
    assert s.session_id == 'o1'
    assert s.status == OrderStatus.PENDING_NOT_SENT

    # Test missing required field (KeyError)
    item_bad = {'order_id': 'o1'} # missing status, created_at, etc.
    with pytest.raises(KeyError):
        Session.from_ddb(item_bad)
