
import json
import importlib
import time
import pytest
from unittest.mock import MagicMock

# Add local src to path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app
import db
import models
from errors import ExpiredError, InvalidStateError

# Mock tables
@pytest.fixture
def mock_tables():
    global app, db, customer_handlers
    for module_name in ("app", "db", "handlers", "handlers.customer", "handlers.restaurant"):
        sys.modules.pop(module_name, None)
    app = importlib.import_module("app")
    db = importlib.import_module("db")
    customer_handlers = importlib.import_module("handlers.customer")

    db.orders_table = MagicMock()
    db.capacity_table = MagicMock()
    db.config_table = MagicMock()
    db.idempotency_table = MagicMock()
    return db

def _make_event(route, body=None, path_params=None, role=None):
    path_params = path_params or {}
    if role is None:
        role = 'restaurant_admin' if '/v1/restaurants/' in route else 'customer'

    claims = {'sub': 'cust_123', 'custom:role': role}
    if role == 'restaurant_admin':
        claims['custom:restaurant_id'] = path_params.get('restaurant_id', 'rest_1')

    return {
        'routeKey': route,
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params,
        'requestContext': {
            'authorizer': {'jwt': {'claims': claims}}
        }
    }

class TestProductionReadiness:
    """Verifies P0 fixes for Production Readiness."""

    def test_update_status_enforces_state_machine(self, mock_tables):
        """Verify update_order_status blocks invalid transitions."""
        order_id = "ord_1"
        # Mock session at PENDING
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'status': 'PENDING_NOT_SENT',
                'restaurant_id': 'rest_1',
                'customer_id': 'cust_123',
                'expires_at': int(time.time()) + 300
            }
        }

        # Try jumping to COMPLETED (Illegal)
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'COMPLETED'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_1'}
        )
        
        # Should raise InvalidStateError -> 409
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409
        assert 'invalid state transition' in resp['body']

    def test_update_expired_order_vicinity(self, mock_tables):
        """Verify update_vicinity blocks expired orders."""
        order_id = "ord_exp"
        # Mock expired session
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'status': 'SENT_TO_DESTINATION',
                'expires_at': int(time.time()) - 300, # Expired 5 mins ago
                'customer_id': 'cust_123'
            }
        }

        event = _make_event(
            'POST /v1/orders/{order_id}/vicinity',
            body={'event': '5_MIN_OUT'},
            path_params={'order_id': order_id}
        )
        
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409
        assert 'order expired' in resp['body']

    def test_update_expired_order_status(self, mock_tables):
        """Verify update_order_status blocks expired orders."""
        order_id = "ord_exp"
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'status': 'SENT_TO_DESTINATION',
                'restaurant_id': 'rest_1',
                'expires_at': int(time.time()) - 100
            }
        }

        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'IN_PROGRESS'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_1'}
        )

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409
        assert 'order expired' in resp['body']

    def test_update_expired_order_cancel(self, mock_tables):
        """Verify cancel_order blocks expired orders."""
        order_id = "ord_exp"
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'customer_id': 'cust_123',
                'status': 'PENDING_NOT_SENT',
                'expires_at': int(time.time()) - 10
            }
        }

        event = _make_event(
            'POST /v1/orders/{order_id}/cancel',
            path_params={'order_id': order_id}
        )

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409

    def test_vicinity_rollback_on_update_failure(self, mock_tables):
        """Verify capacity is released if order update fails."""
        from unittest.mock import patch
        
        order_id = "ord_rollback"
        # Mock session
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'status': 'PENDING_NOT_SENT',
                'restaurant_id': 'rest_1', 
                'customer_id': 'cust_123',
                'expires_at': int(time.time()) + 300
            }
        }
        
        # Mock update failure
        mock_tables.orders_table.update_item.side_effect = Exception("DB Fail")
        
        # Patch capacity module interacting with handlers.customer
        # Since handlers.customer is imported in app.py, and we are running app.lambda_handler
        # We need to patch where it is used.
        with patch.object(customer_handlers, 'capacity') as mock_cap, \
             patch.object(customer_handlers, 'db', mock_tables): # Ensure handler sees our mock tables
            
            # Setup reservation success
            mock_cap.check_and_reserve_for_arrival.return_value = {
                'reserved': True,
                'window_start': 1000,
                'window_seconds': 300
            }
            
            event = _make_event(
                'POST /v1/orders/{order_id}/vicinity',
                body={'event': '5_MIN_OUT'},
                path_params={'order_id': order_id}
            )
            
            # Expect 500 because exception bubbles up
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
            
            # Verify release_slot was called
            mock_cap.release_slot.assert_called_once()
            args = mock_cap.release_slot.call_args
            # args[0] is table, [1] is dest_id, [2] is window_start
            assert args[0][2] == 1000
