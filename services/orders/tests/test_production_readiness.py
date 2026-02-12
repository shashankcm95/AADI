
import json
import time
import pytest
from unittest.mock import MagicMock
from decimal import Decimal

# Add local src to path for imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

import app
import db
import models
from errors import ExpiredError, InvalidStateError

# Mock tables
@pytest.fixture
def mock_tables():
    db.orders_table = MagicMock()
    db.capacity_table = MagicMock()
    db.config_table = MagicMock()
    db.idempotency_table = MagicMock()
    return db

def _make_event(route, body=None, path_params=None):
    return {
        'routeKey': route,
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'cust_123'}}}
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

    def test_update_expired_order_tip(self, mock_tables):
        """Verify add_tip blocks expired orders."""
        order_id = "ord_exp"
        mock_tables.orders_table.get_item.return_value = {
            'Item': {
                'order_id': order_id,
                'customer_id': 'cust_123',
                'expires_at': int(time.time()) - 10
            }
        }

        event = _make_event(
            'POST /v1/orders/{order_id}/tip',
            body={'tip_cents': 100},
            path_params={'order_id': order_id}
        )

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409

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
