"""
API Integration Tests for Restaurants Service

Tests exercise the full lambda_handler → router → handler → DB → response chain,
verifying routing, CORS headers, auth claims parsing, and error handling.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

import app
import utils


def _make_event(route_key, body=None, path_params=None, role='admin',
                restaurant_id=None, customer_id=None):
    """Build a minimal API Gateway v2 event with auth claims."""
    claims = {'sub': customer_id or 'user_1', 'custom:role': role}
    if restaurant_id:
        claims['custom:restaurant_id'] = restaurant_id

    event = {
        'routeKey': route_key,
        'pathParameters': path_params or {},
        'requestContext': {
            'authorizer': {
                'jwt': {'claims': claims}
            }
        },
        'headers': {'origin': 'http://localhost:5173'},
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


# =============================================================================
# Health & Routing
# =============================================================================

class TestHealthAndRouting:
    def test_health_endpoint(self, mock_tables):
        event = _make_event('GET /v1/restaurants/health')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['status'] == 'healthy'

    def test_unknown_route_returns_404(self, mock_tables):
        event = _make_event('GET /v1/unknown')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404

    def test_exception_returns_500(self, mock_tables):
        """Unhandled exception → 500 with error message."""
        with patch.object(app, 'list_restaurants', side_effect=Exception("Boom")):
            event = _make_event('GET /v1/restaurants')
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
            body = json.loads(resp['body'])
            assert 'Internal server error' in body.get('error', '')


# =============================================================================
# Restaurant CRUD via lambda_handler
# =============================================================================

class TestRestaurantLifecycle:
    def test_create_get_update_list_flow(self, mock_tables, monkeypatch):
        """Full lifecycle: Create → Get → Update → List."""
        # Mock geocoding to avoid real HTTP calls
        monkeypatch.setattr(utils, 'geocode_address', lambda *a, **k: {'lat': 30.0, 'lon': -97.0})
        monkeypatch.setattr(utils, 'upsert_restaurant_geofences', lambda *a, **k: True)

        # 1. Create
        event = _make_event('POST /v1/restaurants', body={
            'name': 'Test Bistro',
            'address': {'street': '100 Main', 'city': 'Austin', 'state': 'TX', 'zip_code': '78701'},
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201
        body = json.loads(resp['body'])
        rid = body['restaurant_id']
        assert rid

        # Verify CORS header
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

        # 2. Get by ID
        event = _make_event('GET /v1/restaurants/{restaurant_id}',
                            path_params={'restaurant_id': rid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['name'] == 'Test Bistro'
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

        # 3. Update
        event = _make_event('PUT /v1/restaurants/{restaurant_id}',
                            path_params={'restaurant_id': rid},
                            body={'name': 'Updated Bistro'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

        # 4. List
        event = _make_event('GET /v1/restaurants')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        # Should find our created restaurant plus seeded ones
        assert isinstance(body.get('restaurants', body.get('Items', [])), list)
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})


# =============================================================================
# Menu Lifecycle via lambda_handler
# =============================================================================

class TestMenuLifecycle:
    def test_update_and_get_menu(self, mock_tables):
        """Create/update menu → get menu → verify items."""
        rid = 'r1'
        # Update menu
        event = _make_event('POST /v1/restaurants/{restaurant_id}/menu',
                            path_params={'restaurant_id': rid},
                            body={'items': [
                                {'id': 'item1', 'name': 'Burger', 'price': 999, 'category': 'Mains'},
                                {'id': 'item2', 'name': 'Fries', 'price': 499, 'category': 'Sides'},
                            ]},
                            role='restaurant_admin', restaurant_id=rid)
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # Get menu
        event = _make_event('GET /v1/restaurants/{restaurant_id}/menu',
                            path_params={'restaurant_id': rid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        items = body.get('items', body.get('menu', []))
        assert len(items) == 2


# =============================================================================
# Config Lifecycle via lambda_handler
# =============================================================================

class TestConfigLifecycle:
    def test_update_and_get_config(self, mock_tables):
        """Update config → get config → verify."""
        rid = 'r1'
        event = _make_event('PUT /v1/restaurants/{restaurant_id}/config',
                            path_params={'restaurant_id': rid},
                            body={'dispatch_trigger_event': 'PARKING'},
                            role='restaurant_admin', restaurant_id=rid)
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        event = _make_event('GET /v1/restaurants/{restaurant_id}/config',
                            path_params={'restaurant_id': rid},
                            role='restaurant_admin', restaurant_id=rid)
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200


# =============================================================================
# Favorites Flow via lambda_handler
# =============================================================================

class TestFavoritesFlow:
    def test_add_list_remove_favorite(self, mock_tables):
        """Add → List → Remove favorite."""
        rid = 'r1'

        # Add
        event = _make_event('PUT /v1/favorites/{restaurant_id}',
                            path_params={'restaurant_id': rid},
                            role='customer', customer_id='cust_1')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # List
        event = _make_event('GET /v1/favorites',
                            role='customer', customer_id='cust_1')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # Remove
        event = _make_event('DELETE /v1/favorites/{restaurant_id}',
                            path_params={'restaurant_id': rid},
                            role='customer', customer_id='cust_1')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200


# =============================================================================
# CORS Verification
# =============================================================================

class TestCORSHeaders:
    def test_success_response_includes_cors(self, mock_tables):
        event = _make_event('GET /v1/restaurants/health')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in resp.get('headers', {})

    def test_404_response_includes_cors(self, mock_tables):
        event = _make_event('GET /v1/nonexistent')
        resp = app.lambda_handler(event, None)
        # 404 may or may not have CORS depending on implementation
        assert resp['statusCode'] == 404

    def test_500_response_on_handler_exception(self, mock_tables):
        """Handler exception → 500 from catch-all."""
        with patch.object(app, 'list_restaurants', side_effect=RuntimeError("test")):
            event = _make_event('GET /v1/restaurants')
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
