"""
API Integration Tests for POS Integration Service

Tests exercise the full lambda_handler → auth → router → handler → DB → response chain,
verifying authentication, permission checking, routing, and error handling.
"""

import json
import hashlib
import importlib
import pytest
from unittest.mock import MagicMock, patch

import app
import auth
import handlers


def _hash_key(raw_key):
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


@pytest.fixture
def mock_auth_db():
    """Mock auth keys_table so authenticate_request returns controlled key records.

    Re-imports auth to handle cases where conftest module clearing
    has created a stale reference.
    """
    active_auth = importlib.import_module("auth")
    original_keys_table = active_auth.keys_table
    mock_table = MagicMock()

    # Default: return a valid full-permission key
    mock_table.get_item.return_value = {
        'Item': {
            'api_key': _hash_key('valid-key'),
            'restaurant_id': 'rest_pos1',
            'pos_system': 'generic',
            'permissions': ['orders:read', 'orders:write', 'menu:read', 'menu:write'],
        }
    }
    active_auth.keys_table = mock_table
    yield mock_table
    active_auth.keys_table = original_keys_table


def _make_event(route_key, body=None, api_key='valid-key', path_params=None, query_params=None):
    """Build a POS API event with authentication header."""
    return {
        'routeKey': route_key,
        'headers': {'X-POS-API-Key': api_key},
        'body': json.dumps(body) if body else None,
        'pathParameters': path_params,
        'queryStringParameters': query_params,
    }


# =============================================================================
# Auth Enforcement
# =============================================================================

class TestAuthEnforcement:
    def test_missing_api_key_returns_401(self, mock_db, mock_auth_db):
        event = _make_event('GET /v1/pos/orders', api_key='')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 401
        body = json.loads(resp['body'])
        assert 'Unauthorized' in body.get('error', '')

    def test_invalid_api_key_returns_401(self, mock_db, mock_auth_db):
        mock_auth_db.get_item.return_value = {}  # Key not found
        event = _make_event('GET /v1/pos/orders', api_key='bad-key-123')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 401

    def test_no_header_returns_401(self, mock_db, mock_auth_db):
        event = {
            'routeKey': 'GET /v1/pos/orders',
            'headers': {},
            'body': None,
            'pathParameters': None,
            'queryStringParameters': None,
        }
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 401


# =============================================================================
# Permission Enforcement
# =============================================================================

class TestPermissionEnforcement:
    def test_read_only_key_cannot_create_orders(self, mock_db, mock_auth_db):
        """Key with only menu:read → POST orders returns 403."""
        mock_auth_db.get_item.return_value = {
            'Item': {
                'api_key': _hash_key('read-key'),
                'restaurant_id': 'rest_pos1',
                'permissions': ['menu:read'],
            }
        }
        event = _make_event('POST /v1/pos/orders', body={
            'pos_order_ref': 'POS-001',
            'items': [{'id': 'i1', 'name': 'Burger', 'qty': 1, 'price_cents': 999}],
        }, api_key='read-key')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 403
        body = json.loads(resp['body'])
        assert 'orders:write' in body.get('message', '')

    def test_orders_key_cannot_sync_menu(self, mock_db, mock_auth_db):
        """Key with orders:write but no menu:write → sync menu returns 403."""
        mock_auth_db.get_item.return_value = {
            'Item': {
                'api_key': _hash_key('orders-key'),
                'restaurant_id': 'rest_pos1',
                'permissions': ['orders:read', 'orders:write'],
            }
        }
        event = _make_event('POST /v1/pos/menu/sync', body={
            'items': [{'id': 'm1', 'name': 'Pizza', 'price_cents': 1299}],
        }, api_key='orders-key')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 403


# =============================================================================
# Order Lifecycle via lambda_handler
# =============================================================================

class TestOrderLifecycle:
    def test_create_list_update_get_flow(self, mock_db, mock_auth_db):
        """Create order → List orders → Update status → verify."""
        # 1. Create order via webhook (returns arrive_order_id not order_id)
        event = _make_event('POST /v1/pos/webhook', body={
            'event_type': 'order.created',
            'webhook_id': 'wh_lifecycle_1',
            'data': {
                'pos_order_ref': 'POS-LIFE-001',
                'items': [{'id': 'i1', 'name': 'Pasta', 'qty': 2, 'price_cents': 1500}],
            }
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] in (200, 201)
        body = json.loads(resp['body'])
        order_id = body.get('arrive_order_id') or body.get('order_id')
        assert order_id

        # 2. List orders (POS format uses arrive_order_id)
        event = _make_event('GET /v1/pos/orders')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        orders = body.get('orders', [])
        assert any(o.get('arrive_order_id') == order_id for o in orders)

        # 3. Update status
        event = _make_event('POST /v1/pos/orders/{order_id}/status',
                            body={'status': 'SENT_TO_DESTINATION'},
                            path_params={'order_id': order_id})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200


# =============================================================================
# Menu Sync Flow via lambda_handler
# =============================================================================

class TestMenuSyncFlow:
    def test_sync_disabled_returns_409(self, mock_db, mock_auth_db):
        """Menu sync disabled by default → 409."""
        event = _make_event('POST /v1/pos/menu/sync', body={
            'items': [
                {'id': 'm1', 'name': 'Burger', 'price_cents': 999, 'category': 'Mains'},
            ]
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409
        body = json.loads(resp['body'])
        assert 'disabled' in body.get('error', '').lower()

    def test_sync_and_get_menu_when_enabled(self, mock_db, mock_auth_db):
        """With POS_MENU_SYNC_ENABLED=true: Sync menu → Get menu → verify items match."""
        with patch.object(handlers, 'POS_MENU_SYNC_ENABLED', True):
            # Sync
            event = _make_event('POST /v1/pos/menu/sync', body={
                'items': [
                    {'id': 'm1', 'name': 'Burger', 'price_cents': 999, 'category': 'Mains'},
                    {'id': 'm2', 'name': 'Fries', 'price_cents': 499, 'category': 'Sides'},
                ]
            })
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 200

        # Get menu (doesn't need sync enabled)
        event = _make_event('GET /v1/pos/menu')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        menu = body.get('menu', [])
        assert len(menu) == 2


# =============================================================================
# Webhook Idempotency via lambda_handler
# =============================================================================

class TestWebhookIdempotency:
    def test_duplicate_webhook_returns_already_processed(self, mock_db, mock_auth_db):
        """Same webhook_id twice → first 201, second 200 with already_processed."""
        webhook_body = {
            'event_type': 'order.created',
            'webhook_id': 'wh_dedup_test_1',
            'data': {
                'pos_order_ref': 'POS-DEDUP-001',
                'items': [{'id': 'i1', 'name': 'Soup', 'qty': 1, 'price_cents': 700}],
            }
        }

        # First call
        event = _make_event('POST /v1/pos/webhook', body=webhook_body)
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] in (200, 201)

        # Second call — same webhook_id
        event = _make_event('POST /v1/pos/webhook', body=webhook_body)
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body.get('status') == 'already_processed'


# =============================================================================
# Routing
# =============================================================================

class TestRouting:
    def test_unknown_route_returns_404(self, mock_db, mock_auth_db):
        event = _make_event('GET /v1/pos/nonexistent')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404

    def test_force_fire_routes_correctly(self, mock_db, mock_auth_db):
        """POST /v1/pos/orders/{order_id}/fire → routes to handle_force_fire."""
        # Create an order first
        mock_db['orders'].items['ord_ff'] = {
            'order_id': 'ord_ff',
            'restaurant_id': 'rest_pos1',
            'status': 'PENDING_NOT_SENT',
            'pos_order_ref': 'POS-FF-001',
        }

        event = _make_event('POST /v1/pos/orders/{order_id}/fire',
                            path_params={'order_id': 'ord_ff'})
        resp = app.lambda_handler(event, None)
        # Should route to handler (200 or state-dependent error)
        assert resp['statusCode'] in (200, 409)
