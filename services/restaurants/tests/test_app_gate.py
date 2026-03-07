"""
Inactive Restaurant Admin Gate Tests

Tests the security-critical inactive-restaurant gate in app.py (lines 33-61):
  - Inactive restaurant_admin: GET/PUT own restaurant allowed, other routes blocked
  - Active restaurant_admin: all routes pass through
  - Non restaurant_admin roles: gate doesn't apply
  - DB lookup failure → 500
"""

import json
from unittest.mock import patch, MagicMock

import app
import utils


def _make_event(route_key, role='restaurant_admin', restaurant_id='rest_1', path_params=None):
    """Build a Lambda event with JWT claims."""
    event = {
        'routeKey': route_key,
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user_1',
                        'custom:role': role,
                    }
                }
            }
        },
        'headers': {'origin': 'http://localhost:5173'},
        'pathParameters': path_params or {},
        'body': '{}',
    }
    if restaurant_id:
        event['requestContext']['authorizer']['jwt']['claims']['custom:restaurant_id'] = restaurant_id
    return event


class TestInactiveGate:
    """Tests for the inactive restaurant_admin access gate."""

    def test_inactive_admin_get_restaurants_allowed(self, mock_tables):
        """Inactive admin can list restaurants."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('GET /v1/restaurants')

        with patch.object(app, 'list_restaurants', return_value={'statusCode': 200, 'body': '[]'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_inactive_admin_get_own_restaurant_allowed(self, mock_tables):
        """Inactive admin can GET own restaurant by ID."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('GET /v1/restaurants/{restaurant_id}',
                            path_params={'restaurant_id': 'rest_1'})

        with patch.object(app, 'get_restaurant', return_value={'statusCode': 200, 'body': '{}'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_inactive_admin_put_own_restaurant_allowed(self, mock_tables):
        """Inactive admin can update own restaurant profile."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('PUT /v1/restaurants/{restaurant_id}',
                            path_params={'restaurant_id': 'rest_1'})
        event['body'] = json.dumps({'name': 'Updated Name'})

        with patch.object(app, 'update_restaurant', return_value={'statusCode': 200, 'body': '{}'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_inactive_admin_post_menu_blocked(self, mock_tables):
        """Inactive admin cannot update menu."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('POST /v1/restaurants/{restaurant_id}/menu',
                            path_params={'restaurant_id': 'rest_1'})

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 403
        body = json.loads(resp['body'])
        assert 'inactive' in body.get('error', '').lower()

    def test_inactive_admin_put_config_blocked(self, mock_tables):
        """Inactive admin cannot update config."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('PUT /v1/restaurants/{restaurant_id}/config',
                            path_params={'restaurant_id': 'rest_1'})

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 403

    def test_inactive_admin_delete_restaurant_blocked(self, mock_tables):
        """Inactive admin cannot delete restaurant."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': False
        }
        event = _make_event('DELETE /v1/restaurants/{restaurant_id}',
                            path_params={'restaurant_id': 'rest_1'})

        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 403

    def test_active_admin_all_routes_allowed(self, mock_tables):
        """Active restaurant_admin passes through the gate for all routes."""
        mock_tables['restaurants'].items['rest_1'] = {
            'restaurant_id': 'rest_1', 'name': 'Test', 'active': True
        }
        event = _make_event('POST /v1/restaurants/{restaurant_id}/menu',
                            path_params={'restaurant_id': 'rest_1'})

        with patch.object(app, 'update_menu', return_value={'statusCode': 200, 'body': '{}'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_platform_admin_bypasses_gate(self, mock_tables):
        """Platform admin (role=admin) is not subject to the gate."""
        event = _make_event('POST /v1/restaurants', role='admin', restaurant_id=None)
        event['body'] = json.dumps({'name': 'New Rest'})

        with patch.object(app, 'create_restaurant', return_value={'statusCode': 201, 'body': '{}'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201

    def test_customer_role_bypasses_gate(self, mock_tables):
        """Customer role is not subject to the gate."""
        event = _make_event('GET /v1/restaurants', role='customer', restaurant_id=None)

        with patch.object(app, 'list_restaurants', return_value={'statusCode': 200, 'body': '[]'}):
            resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_db_lookup_failure_returns_500(self, mock_tables):
        """Exception during restaurant status check → 500."""
        # Patch restaurants_table to raise on get_item
        original = utils.restaurants_table
        failing_table = MagicMock()
        failing_table.get_item.side_effect = Exception("DDB timeout")

        # Patch on both app and utils modules
        utils.restaurants_table = failing_table
        app_restaurants_attr = getattr(app, 'restaurants_table', None)
        if hasattr(app, 'restaurants_table'):
            app.restaurants_table = failing_table

        try:
            event = _make_event('GET /v1/restaurants')
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 500
            body = json.loads(resp['body'])
            assert 'Internal authorization error' in body.get('error', '')
        finally:
            utils.restaurants_table = original
            if app_restaurants_attr is not None:
                app.restaurants_table = app_restaurants_attr
